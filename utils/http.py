import time
from typing import Any, Dict, Optional, Tuple

import requests


class HTTPError(Exception):
    pass


def request_with_retry(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    data: Optional[Any] = None,
    timeout: int = 30,
    retries: int = 3,
    backoff_factor: float = 0.6,
) -> Tuple[requests.Response, float]:
    """
    发送HTTP请求并带重试，返回(response, elapsed_ms)。
    对非2xx状态码不抛异常，交由调用方处理。
    """
    sess = requests.Session()
    last_exc = None
    for attempt in range(1, retries + 1):
        start = time.perf_counter()
        try:
            resp = sess.request(
                method=method.upper(),
                url=url,
                headers=headers,
                params=params,
                json=json,
                data=data,
                timeout=timeout,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            return resp, elapsed_ms
        except requests.RequestException as e:
            last_exc = e
            if attempt >= retries:
                raise e
            time.sleep(backoff_factor * attempt)
    # 理论上不会到达这里
    raise HTTPError(str(last_exc) if last_exc else '未知HTTP错误')