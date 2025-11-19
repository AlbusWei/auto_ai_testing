from typing import List, Tuple, Optional

import pandas as pd

from utils.http import request_with_retry
from utils.logger import get_logger
from utils.parsers import parse_label_from_judge_response, parse_model_output
from utils.files import derive_output_path, detect_file_type, ensure_dir
from utils.streaming import open_stream_writer


logger = get_logger(__name__)


# ------------- Streaming writer moved to utils.streaming -------------


def _headers(api_key: str) -> dict:
    h = {
        'Content-Type': 'application/json',
    }
    if api_key:
        h['Authorization'] = f'Bearer {api_key}'
    return h


def _build_single_input(gt: str, out: str) -> str:
    return f"ground_truth: {gt}\noutput: {out}"


def evaluate(
    df: pd.DataFrame,
    copied_dataset_path: str,
    endpoint: str,
    api_key: str,
    *,
    batch_size: int = 1,
    max_merge_rows: int = 1,
    timeout: int = 30,
    retries: int = 3,
    base_name: str,
    judge_kind: str = 'dify_workflow',
    user_id: str = 'auto-ai-testing',
    evaluation_results_dir: str = 'evaluation_results',
) -> Tuple[pd.DataFrame, str]:
    """
    调用裁判API为每行生成label。支持批量(列表结构)或单行文本拼接结构。
    返回(评估后的数据框, 保存路径)。
    """
    results = df.copy()
    results['judge_elapsed_ms'] = None
    results['judge_status'] = None
    results['judge_error'] = None
    if 'judge_answer' not in results.columns:
        results['judge_answer'] = None
    if 'label' not in results.columns:
        results['label'] = None

    # Prepare streaming writer and output path (atomic header creation)
    ensure_dir(evaluation_results_dir)
    ftype = detect_file_type(copied_dataset_path)
    ext = '.csv' if ftype == 'csv' else '.xlsx'
    out_path = derive_output_path(evaluation_results_dir, base_name, 'evaluation', ext)
    cols = list(results.columns)
    writer = None
    try:
        # 尝试初始化流式写入器（原子创建+锁）
        writer = open_stream_writer('csv' if ftype == 'csv' else 'excel', out_path, cols)
    except Exception as e:
        logger.warning(f'初始化评估流式写入失败，将回退为一次性写入: {e}')
        writer = None

    n = len(results)
    i = 0
    while i < n:
        group_end = min(i + max(1, max_merge_rows), n)
        group = results.iloc[i:group_end]
        try:
            # 根据judge_kind构造payload
            if judge_kind == 'dify_workflow':
                if batch_size > 1 or max_merge_rows > 1:
                    items = [
                        {'ground_truth': str(r['ground_truth']), 'output': str(r['output'])}
                        for _, r in group.iterrows()
                    ]
                    payload = {
                        'inputs': {'items': items},
                        'response_mode': 'blocking',
                        'user': user_id,
                    }
                else:
                    payload = {
                        'inputs': {
                            'ground_truth': str(group.iloc[0]['ground_truth']),
                            'output': str(group.iloc[0]['output']),
                        },
                        'response_mode': 'blocking',
                        'user': user_id,
                    }
            elif judge_kind == 'dify_chat':
                # 使用chat-messages，将gt与output拼接到query，同时也放到inputs，便于工作流变量读取
                if len(group) > 1:
                    # 合并为多项文本
                    parts = []
                    for jdx, r in enumerate(group.itertuples()):
                        parts.append(f"[{jdx+1}] ground_truth: {getattr(r, 'ground_truth')}\noutput: {getattr(r, 'output')}")
                    query_text = "\n\n".join(parts)
                else:
                    query_text = _build_single_input(str(group.iloc[0]['ground_truth']), str(group.iloc[0]['output']))
                payload = {
                    'inputs': {},
                    'query': query_text,
                    'response_mode': 'blocking',
                    'user': user_id,
                }
            else:
                # 通用/占位：与旧逻辑兼容
                if batch_size > 1 or max_merge_rows > 1:
                    items = [
                        {'ground_truth': str(r['ground_truth']), 'output': str(r['output'])}
                        for _, r in group.iterrows()
                    ]
                    payload = {'items': items}
                else:
                    payload = {'input': _build_single_input(str(group.iloc[0]['ground_truth']), str(group.iloc[0]['output']))}

            resp, elapsed_ms = request_with_retry(
                'POST', endpoint, headers=_headers(api_key), json=payload, timeout=timeout, retries=retries
            )
            # 记录状态
            for idx in group.index:
                results.at[idx, 'judge_elapsed_ms'] = round(elapsed_ms, 2)
                results.at[idx, 'judge_status'] = resp.status_code

            if 200 <= resp.status_code < 300:
                if judge_kind == 'dify_chat':
                    # 对于chat-messages，优先保留原始answer文本，便于定位问题
                    answer_text = parse_model_output(resp)
                    for idx in group.index:
                        results.at[idx, 'judge_answer'] = answer_text
                    # 当单行处理时，直接将原文贴到label，避免误解析数字
                    if len(group) == 1 and max_merge_rows == 1:
                        for idx in group.index:
                            results.at[idx, 'label'] = answer_text
                    else:
                        # 多行合并场景，无法逐条对应label，广播原文以便人工检查
                        for idx in group.index:
                            results.at[idx, 'label'] = answer_text
                else:
                    label = parse_label_from_judge_response(resp)
                    if isinstance(label, list):
                        # 若数量匹配，逐个赋值；否则广播
                        if len(label) == len(group):
                            for (idx, _), val in zip(group.iterrows(), label):
                                results.at[idx, 'label'] = val
                        else:
                            for idx in group.index:
                                results.at[idx, 'label'] = label[0]
                    else:
                        for idx in group.index:
                            results.at[idx, 'label'] = label
            else:
                err = f'HTTP {resp.status_code}: {resp.text[:200]}'
                for idx in group.index:
                    results.at[idx, 'judge_error'] = err
            i = group_end
        except Exception as e:
            err = f'JudgeException: {str(e)}'
            for idx in group.index:
                results.at[idx, 'judge_error'] = err
            i = group_end

        # stream-append rows after processing each group
        if writer is not None:
            for idx in group.index:
                try:
                    row_vals = [results.at[idx, c] if c in results.columns else None for c in cols]
                    writer.append_row(row_vals)
                except Exception as we:
                    logger.error(f'评估结果写入失败(行id={results.at[idx, "id"]}): {we}')

    # finalize with compatibility
    if writer is not None:
        try:
            writer.close()
        except Exception as e:
            logger.error(f'评估文件关闭失败: {e}')
        logger.info(f'评估文件已保存: {out_path}')
        return results, out_path
    else:
        # 回退到一次性保存逻辑（保持原行为与兼容性）
        try:
            if ftype == 'csv':
                fallback_path = derive_output_path(evaluation_results_dir, base_name, 'evaluation', '.csv')
                results.to_csv(fallback_path, index=False, encoding='utf-8')
            else:
                fallback_path = derive_output_path(evaluation_results_dir, base_name, 'evaluation', '.xlsx')
                results.to_excel(fallback_path, index=False)
            logger.info(f'评估文件已保存(一次性写入): {fallback_path}')
            return results, fallback_path
        except Exception as e:
            logger.error(f'评估文件一次性保存失败: {e}')
            # 返回预期的路径以便上层处理，但文件可能不存在
            return results, out_path