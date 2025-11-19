import os
import csv
import tempfile
import time
from typing import Dict, Tuple, Optional, List

import pandas as pd

from utils.http import request_with_retry
from utils.logger import get_logger
from utils.parsers import parse_model_output, parse_dify_metadata
from utils.files import derive_output_path, detect_file_type, ensure_dir
from utils.streaming import open_stream_writer


logger = get_logger(__name__)


# ------------- Streaming writer moved to utils.streaming -------------


def _headers(api_key: str) -> Dict[str, str]:
    h = {
        'Content-Type': 'application/json',
    }
    if api_key:
        h['Authorization'] = f'Bearer {api_key}'
    return h


def run_model(
    df: pd.DataFrame,
    endpoint: str,
    api_key: str,
    *,
    input_field: str = 'input',
    timeout: int = 30,
    retries: int = 3,
    model_kind: str = 'generic',
    user_id: str = 'auto-ai-testing',
    conversation_id: str = '',
    dify_inputs: Optional[Dict[str, str]] = None,
    files: Optional[List[Dict[str, str]]] = None,
    detail: bool = False,
    # streaming options (optional): when provided, enable atomic header creation and per-row append
    stream_output_dir: Optional[str] = None,
    stream_base_name: Optional[str] = None,
    copied_dataset_path: Optional[str] = None,
) -> pd.DataFrame:
    """对数据集逐行调用模型API，写入output并记录耗时与状态。支持Dify completion/chat与通用JSON。"""
    results = df.copy()
    results['request_started_at'] = None
    results['request_elapsed_ms'] = None
    results['response_status'] = None
    results['error'] = None
    # Dify元数据列（仅在detail模式下写入）
    if detail:
        for col in [
            'conversation_id', 'task_id', 'message_id', 'mode',
            'usage_prompt_tokens', 'usage_completion_tokens', 'usage_total_tokens', 'usage_total_price', 'usage_currency', 'usage_latency'
        ]:
            if col not in results.columns:
                results[col] = None

    # streaming writer init (optional)
    writer = None
    cols = list(results.columns)
    try:
        if stream_output_dir and stream_base_name and copied_dataset_path:
            ftype = detect_file_type(copied_dataset_path)
            ext = '.csv' if ftype == 'csv' else '.xlsx'
            out_path = derive_output_path(stream_output_dir, stream_base_name, 'outputs', ext)
            # store path for downstream save_outputs compatibility
            results.attrs['stream_out_path'] = out_path
            results.attrs['stream_file_type'] = ftype
            # 尝试初始化流式写入器（原子创建+锁）
            writer = open_stream_writer('csv' if ftype == 'csv' else 'excel', out_path, cols)
    except Exception as e:
        logger.warning(f'初始化流式写入失败，降级为内存累积: {e}')
        writer = None

    for idx, row in results.iterrows():
        inp = row['input']
        # 根据model_kind构造payload
        if model_kind == 'dify_completion':
            # 参照 Dify completion-messages
            payload = {
                'inputs': {input_field: inp, **(dify_inputs or {})},  # 通常 input_field='text'
                'response_mode': 'blocking',
                'user': user_id,
            }
            if files:
                payload['files'] = files
        elif model_kind == 'dify_chat':
            inputs_payload = dict(dify_inputs or {})
            lang_val = None
            if 'lang' in results.columns and not pd.isna(row.get('lang')):
                lang_val = str(row.get('lang')).strip()
            city_val = None
            if 'city' in results.columns and not pd.isna(row.get('city')):
                city_val = str(row.get('city')).strip()

            if city_val:
                inputs_payload['function_name'] = 'poi'
                inputs_payload['city'] = city_val
                query_val = f'["{str(inp)}"]'
            else:
                inputs_payload['function_name'] = 'intention'
                query_val = str(inp)

            if lang_val:
                inputs_payload['lang'] = lang_val

            payload = {
                'inputs': inputs_payload,
                'query': query_val,
                'response_mode': 'blocking',
                'conversation_id': conversation_id or '',
                'user': user_id,
            }
            if files:
                payload['files'] = files
        else:
            payload = {input_field: inp}
        results.at[idx, 'request_started_at'] = pd.Timestamp.utcnow().isoformat()
        try:
            resp, elapsed_ms = request_with_retry(
                'POST', endpoint, headers=_headers(api_key), json=payload, timeout=timeout, retries=retries
            )
            results.at[idx, 'request_elapsed_ms'] = round(elapsed_ms, 2)
            results.at[idx, 'response_status'] = resp.status_code
            if 200 <= resp.status_code < 300:
                out_text = parse_model_output(resp)
                results.at[idx, 'output'] = out_text
                # 提取Dify元数据（detail模式）
                if detail:
                    meta = parse_dify_metadata(resp)
                    for k, v in meta.items():
                        if f'{k}' in results.columns:
                            results.at[idx, f'{k}'] = v
            else:
                results.at[idx, 'error'] = f'HTTP {resp.status_code}: {resp.text[:200]}'
                if pd.isna(results.at[idx, 'output']):
                    results.at[idx, 'output'] = ''
        except Exception as e:
            results.at[idx, 'request_elapsed_ms'] = None
            results.at[idx, 'response_status'] = None
            results.at[idx, 'error'] = f'RequestException: {str(e)}'
            if pd.isna(results.at[idx, 'output']):
                results.at[idx, 'output'] = ''
        # 流式追加写入：每行写入后立即持久化
        if writer is not None:
            try:
                # 顺序严格按照列顺序写入
                row_vals = [results.at[idx, c] if c in results.columns else None for c in cols]
                writer.append_row(row_vals)
            except Exception as we:
                logger.error(f"写入结果文件失败(行id={row['id']}): {we}")
        logger.info(f"行id={row['id']} 已处理")
    try:
        if writer is not None:
            writer.close()
    except Exception:
        pass
    return results


def save_outputs(results: pd.DataFrame, copied_dataset_path: str, output_dir: str, base_name: str) -> Tuple[str, str]:
    """保存输出文件。若已启用流式写入，则直接返回该文件路径；否则按原逻辑一次性保存。
    返回(路径, 文件类型)。
    """
    ensure_dir(output_dir)
    ftype = detect_file_type(copied_dataset_path)
    # if run_model used streaming, reuse its path
    stream_path = results.attrs.get('stream_out_path')
    stream_ftype = results.attrs.get('stream_file_type')
    if stream_path and stream_ftype == ftype and os.path.exists(stream_path):
        logger.info(f'检测到流式写入文件，跳过重写: {stream_path}')
        return stream_path, ftype
    # fallback to one-shot save
    if ftype == 'csv':
        out_path = derive_output_path(output_dir, base_name, 'outputs', '.csv')
        results.to_csv(out_path, index=False, encoding='utf-8')
    else:
        out_path = derive_output_path(output_dir, base_name, 'outputs', '.xlsx')
        results.to_excel(out_path, index=False)
    logger.info(f'输出文件已保存: {out_path}')
    return out_path, ftype