import json
import re
from typing import Any, Dict, List, Optional, Union

import requests


def _safe_json(response: requests.Response) -> Optional[Dict[str, Any]]:
    try:
        return response.json()
    except Exception:
        try:
            return json.loads(response.text)
        except Exception:
            return None


def parse_model_output(response: requests.Response) -> str:
    """
    尝试从模型响应中提取文本输出。
    支持常见JSON结构与纯文本。
    """
    ct = response.headers.get('Content-Type', '')
    if 'application/json' in ct:
        j = _safe_json(response) or {}
        # 常见键路径尝试
        for path in [
            ('output',),
            ('data', 'output'),
            ('result',),
            ('choices', 0, 'message', 'content'),
            ('choices', 0, 'text'),
            ('message',),
            ('text',),
            ('answer',),
            ('data', 'answer'),
            ('outputs', 'answer'),
            ('outputs', 'output_text'),
        ]:
            try:
                val: Any = j
                for key in path:
                    if isinstance(key, int):
                        val = val[key]
                    else:
                        val = val.get(key) if isinstance(val, dict) else None
                if isinstance(val, str):
                    # 针对Dify的answer字符串，若其内容为JSON，优先提取其中的message字段
                    if 'answer' in path:
                        s = val.strip()
                        if (s.startswith('{') and s.endswith('}')) or (s.startswith('[') and s.endswith(']')):
                            try:
                                obj = json.loads(s)
                                msg = obj.get('message')
                                if isinstance(msg, str):
                                    return msg
                            except Exception:
                                pass
                    return val
                # 若answer为对象，直接提取message
                if isinstance(val, dict):
                    msg = val.get('message')
                    if isinstance(msg, str):
                        return msg
            except Exception:
                continue
        # 如果找不到，退回字符串化
        return json.dumps(j, ensure_ascii=False)
    # 非JSON，返回原始文本
    return response.text


def parse_label_from_judge_response(response: requests.Response) -> Union[int, float, List[Union[int, float]]]:
    """
    从裁判响应中解析标签：支持单值或列表，优先0/1，兼容连续分值。
    兼容返回结构：{"score":1}、{"data":{"score":1}}、{"data":[{"score":1},...]}
    若纯文本，提取第一个0/1或浮点数。
    """
    ct = response.headers.get('Content-Type', '')
    j = _safe_json(response)
    if j is not None:
        # 单值
        for path in [
            ('score',), ('data', 'score'), ('result', 'score'), ('outputs', 'score'), ('answer',), ('data', 'answer')
        ]:
            try:
                val: Any = j
                for key in path:
                    val = val.get(key) if isinstance(val, dict) else None
                if isinstance(val, (int, float)):
                    return val
                if isinstance(val, str):
                    # 从字符串中提取第一个数字作为评分
                    import re
                    m = re.search(r"[-+]?\d*\.\d+|\d+", val)
                    if m:
                        n = float(m.group(0))
                        return int(n) if abs(n - int(n)) < 1e-9 else n
            except Exception:
                continue
        # 列表
        for path in [('data',), ('scores',), ('result', 'scores')]:
            try:
                val: Any = j
                for key in path:
                    val = val.get(key) if isinstance(val, dict) else None
                if isinstance(val, list):
                    scores: List[Union[int, float]] = []
                    for item in val:
                        if isinstance(item, dict):
                            s = item.get('score')
                            if isinstance(s, (int, float)):
                                scores.append(s)
                        elif isinstance(item, (int, float)):
                            scores.append(item)
                    if scores:
                        return scores
            except Exception:
                continue
        # 兜底：若JSON包含单一数字键
        for k, v in j.items():
            if isinstance(v, (int, float)):
                return v
    # 纯文本：提取数字
    text = response.text
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", text)
    if not nums:
        raise ValueError('无法从裁判响应解析评分结果')
    # 若只有一个数字，返回单值
    if len(nums) == 1:
        n = float(nums[0])
        return int(n) if abs(n - int(n)) < 1e-9 else n
    # 多个数字，返回列表
    out: List[Union[int, float]] = []
    for s in nums:
        n = float(s)
        out.append(int(n) if abs(n - int(n)) < 1e-9 else n)
    return out


def parse_dify_metadata(response: requests.Response) -> Dict[str, Any]:
    """解析Dify响应中的元数据与会话信息。"""
    meta: Dict[str, Any] = {}
    j = _safe_json(response) or {}
    if not isinstance(j, dict):
        return meta
    # 顶层会话信息
    for k in ['conversation_id', 'task_id', 'message_id', 'mode', 'event', 'id', 'created_at']:
        if k in j:
            meta[k] = j.get(k)
    # usage
    usage = None
    try:
        usage = j.get('metadata', {}).get('usage')
    except Exception:
        usage = None
    if isinstance(usage, dict):
        for k in [
            'prompt_tokens', 'completion_tokens', 'total_tokens', 'total_price', 'currency', 'latency',
            'prompt_unit_price', 'completion_unit_price', 'prompt_price', 'completion_price', 'prompt_price_unit', 'completion_price_unit'
        ]:
            if k in usage:
                meta[f'usage_{k}'] = usage.get(k)
    return meta