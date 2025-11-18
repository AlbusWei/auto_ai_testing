from typing import List, Tuple

import pandas as pd

from utils.http import request_with_retry
from utils.logger import get_logger
from utils.parsers import parse_label_from_judge_response
from utils.files import derive_output_path, detect_file_type, ensure_dir


logger = get_logger(__name__)


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

    # 保存
    ensure_dir(evaluation_results_dir)
    ftype = detect_file_type(copied_dataset_path)
    if ftype == 'csv':
        out_path = derive_output_path(evaluation_results_dir, base_name, 'evaluation', '.csv')
        results.to_csv(out_path, index=False, encoding='utf-8')
    else:
        out_path = derive_output_path(evaluation_results_dir, base_name, 'evaluation', '.xlsx')
        results.to_excel(out_path, index=False)
    logger.info(f'评估文件已保存: {out_path}')
    return results, out_path