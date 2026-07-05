"""Resilient HTTP client: retry on 429/5xx, pagination, structured errors."""
import time
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import structlog

log = structlog.get_logger()
BASE = "https://management.azure.com"


class AzureAPIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status  = status
        self.code    = code
        self.message = message
        super().__init__(f"[{status}] {code}: {message}")


def _raise_for(resp: requests.Response):
    if resp.ok:
        return
    try:
        body = resp.json()
        err  = body.get("error", {})
        code = err.get("code", "Unknown")
        msg  = err.get("message", resp.text[:400])
    except Exception:
        code, msg = "ParseError", resp.text[:400]
    raise AzureAPIError(resp.status_code, code, msg)


@retry(
    retry=retry_if_exception_type(AzureAPIError),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
def _get(url: str, headers: dict, params: dict = None) -> dict:
    resp = requests.get(url, headers=headers, params=params, timeout=60)
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 10))
        log.warning("rate_limited", retry_after=retry_after, url=url)
        time.sleep(retry_after)
        raise AzureAPIError(429, "RateLimited", "Retry-After")
    _raise_for(resp)
    return resp.json()


@retry(
    retry=retry_if_exception_type(AzureAPIError),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    reraise=True,
)
def _post(url: str, headers: dict, payload: dict) -> dict:
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 10))
        log.warning("rate_limited", retry_after=retry_after, url=url)
        time.sleep(retry_after)
        raise AzureAPIError(429, "RateLimited", "Retry-After")
    _raise_for(resp)
    return resp.json()


def get_all_pages(url: str, headers: dict, params: dict = None) -> list:
    """Auto-paginate ARM list responses following nextLink."""
    results = []
    next_url = url
    while next_url:
        data = _get(next_url, headers, params if next_url == url else None)
        results.extend(data.get("value", []))
        next_url = data.get("nextLink")
    return results
