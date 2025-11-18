import os
from typing import Dict, Tuple, Optional, List

import pandas as pd

from utils.http import request_with_retry
from utils.logger import get_logger
from utils.parsers import parse_model_output, parse_dify_metadata
from utils.files import derive_output_path, detect_file_type, ensure_dir


logger = get_logger(__name__)


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
) -> pd.DataFrame:
    """对数据集逐行调用模型API，写入output并记录耗时与状态。支持Dify completion/chat与通用JSON。"""
    results = df.copy()
    results['request_started_at'] = None
    results['request_elapsed_ms'] = None
    results['response_status'] = None
    results['error'] = None
    # Dify元数据列（若可用）
    for col in [
        'conversation_id', 'task_id', 'message_id', 'mode',
        'usage_prompt_tokens', 'usage_completion_tokens', 'usage_total_tokens', 'usage_total_price', 'usage_currency', 'usage_latency'
    ]:
        if col not in results.columns:
            results[col] = None

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
            payload = {
                'inputs': dify_inputs or {},
                'query': inp,
                'response_mode': 'blocking',
                'user': user_id,
            }
            if conversation_id:
                payload['conversation_id'] = conversation_id
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
                # 提取Dify元数据
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
        logger.info(f"行id={row['id']} 已处理")
    return results


def save_outputs(results: pd.DataFrame, copied_dataset_path: str, output_dir: str, base_name: str) -> Tuple[str, str]:
    """根据原文件类型，保存到output_results目录，返回(路径, 文件类型)。"""
    ensure_dir(output_dir)
    ftype = detect_file_type(copied_dataset_path)
    if ftype == 'csv':
        out_path = derive_output_path(output_dir, base_name, 'outputs', '.csv')
        results.to_csv(out_path, index=False, encoding='utf-8')
    else:
        out_path = derive_output_path(output_dir, base_name, 'outputs', '.xlsx')
        results.to_excel(out_path, index=False)
    logger.info(f'输出文件已保存: {out_path}')
    return out_path, ftype