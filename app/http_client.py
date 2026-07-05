"""Resilient, self-throttling HTTP client for Azure Resource Manager.

Production-grade rate-limit protection so we never exceed ARM limits no matter
how many endpoints or worker threads fan out. Every ARM GET/POST funnels
through ``_request`` — the single choke point — which applies, in order:

  1. A global token-bucket rate limiter (caps sustained requests/second).
  2. A global concurrency semaphore (caps simultaneous in-flight requests).
  3. Adaptive backoff driven by the ``x-ms-ratelimit-remaining-*`` headers,
     slowing down *before* the subscription read budget is exhausted.
  4. Retry on 429 and 5xx (incl. 502 ProviderError) with exponential backoff
     plus jitter, honoring ``Retry-After``.

``get_all_pages`` additionally caches list results for a short TTL so repeated
enumerations within the window never touch ARM.

All knobs are environment-overridable; defaults are conservative.
"""
import os
import time
import threading
from contextlib import contextmanager
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
)
import structlog

log = structlog.get_logger()
BASE = "https://management.azure.com"

# Transient statuses worth retrying.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool) -> bool:
    val = os.getenv(name, "")
    if not val:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


# ── Tunables (env-overridable) ────────────────────────────────────────────────
_MAX_CONCURRENCY = _int_env("ARM_MAX_CONCURRENCY", 4)        # simultaneous in-flight calls
_RATE_PER_SEC    = _int_env("ARM_REQUESTS_PER_SEC", 4)       # sustained request rate
_BURST           = _int_env("ARM_BURST", 4)                  # token-bucket capacity
_REMAINING_FLOOR = _int_env("ARM_REMAINING_THRESHOLD", 500)  # start slowing below this budget
_MAX_ATTEMPTS    = _int_env("ARM_MAX_ATTEMPTS", 8)
_CACHE_TTL       = _int_env("ARM_CACHE_TTL_SECONDS", 120)    # 0 disables the read cache
_PAGE_DELAY_SEC  = max(0.0, _int_env("ARM_PAGE_DELAY_MS", 150) / 1000.0)


def arm_fetch_workers() -> int:
    """Max parallel subscription list fetches (e.g. analyze). Sequential during patient sync."""
    if arm_patient_active():
        return 1
    return _int_env("ANALYZE_FETCH_WORKERS", _MAX_CONCURRENCY)


class AzureAPIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status  = status
        self.code    = code
        self.message = message
        super().__init__(f"[{status}] {code}: {message}")


class _TokenBucket:
    """Thread-safe token bucket; smooths the request rate to <= rate/second."""

    def __init__(self, rate: float, capacity: float):
        self._rate = float(rate)
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._ts = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(
                    self._capacity, self._tokens + (now - self._ts) * self._rate
                )
                self._ts = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._rate
            time.sleep(wait)


_bucket = _TokenBucket(_RATE_PER_SEC, _BURST)
_slots = threading.BoundedSemaphore(_MAX_CONCURRENCY)

_cache_lock = threading.Lock()
_cache_store: dict = {}  # key -> (expires_at_monotonic, value)

_client_lock = threading.Lock()
_http_client: httpx.Client | None = None
_HTTP2 = _bool_env("ARM_HTTP2", False)
_KEEPALIVE_EXPIRY = max(5.0, float(_int_env("ARM_KEEPALIVE_EXPIRY_SEC", 25)))


def reset_http_client() -> None:
    """Drop the pooled client so the next ARM call opens fresh connections."""
    global _http_client
    with _client_lock:
        if _http_client is not None:
            try:
                _http_client.close()
            except Exception:
                pass
            _http_client = None


def _get_http_client() -> httpx.Client:
    """Shared httpx client with connection pooling.

    HTTP/2 is off by default — multiplexed streams on one TCP connection can all
    fail together when Azure resets the socket (broken pipe / connection reset).
    Set ARM_HTTP2=true to enable HTTP/2.
    """
    global _http_client
    with _client_lock:
        if _http_client is None:
            _http_client = httpx.Client(
                http2=_HTTP2,
                limits=httpx.Limits(
                    max_connections=20,
                    max_keepalive_connections=10,
                    keepalive_expiry=_KEEPALIVE_EXPIRY,
                ),
                timeout=httpx.Timeout(300.0),
            )
        return _http_client

_cooldown_lock = threading.Lock()
_cooldown_until: float = 0.0  # monotonic — all threads pause ARM calls until this time

_patient_lock = threading.Lock()
_patient_depth = 0


def arm_patient_active() -> bool:
    """True during scoped inventory sync — sequential calls, no proactive throttling."""
    if _patient_depth > 0:
        return True
    return os.getenv("ARM_PATIENT_SYNC", "").strip().lower() in {"1", "true", "yes", "on"}


@contextmanager
def arm_patient_sync():
    """Sequential ARM sync: avoid 429s by not racing; honor Retry-After fully on limits."""
    global _patient_depth
    _patient_depth += 1
    try:
        yield
    finally:
        _patient_depth -= 1


def _short_url(url: str) -> str:
    """Trim noisy pagination tokens from log lines."""
    if "?" not in url:
        return url
    base, _, qs = url.partition("?")
    if "skiptoken" in qs.lower() or "nextlink" in qs.lower():
        return f"{base}?…"
    return url


def _wait_for_global_cooldown() -> None:
    """Block all ARM traffic while any thread is serving a Retry-After penalty."""
    while True:
        with _cooldown_lock:
            remaining = _cooldown_until - time.monotonic()
        if remaining <= 0:
            return
        log.info("arm_cooldown_wait", seconds=round(remaining, 1))
        time.sleep(min(remaining, 5.0))


def _extend_global_cooldown(seconds: float) -> None:
    global _cooldown_until
    with _cooldown_lock:
        _cooldown_until = max(_cooldown_until, time.monotonic() + seconds)


def _raise_for(resp: httpx.Response):
    if resp.is_success:
        return
    try:
        body = resp.json()
        err  = body.get("error", {})
        code = err.get("code", "Unknown")
        msg  = err.get("message", resp.text[:400])
    except Exception:
        code, msg = "ParseError", resp.text[:400]
    raise AzureAPIError(resp.status_code, code, msg)


def _adaptive_throttle(resp: httpx.Response) -> None:
    """Proactively pause as the subscription read budget runs low."""
    remaining = (
        resp.headers.get("x-ms-ratelimit-remaining-subscription-reads")
        or resp.headers.get("x-ms-ratelimit-remaining-subscription-resource-requests")
        or resp.headers.get("x-ms-ratelimit-remaining-subscription-global-reads")
    )
    try:
        rem = int(remaining)
    except (TypeError, ValueError):
        return
    if rem < _REMAINING_FLOOR:
        # The closer to zero, the longer we wait (capped at 10s).
        delay = min(10.0, (_REMAINING_FLOOR - rem) / _REMAINING_FLOOR * 10.0)
        log.info("arm_budget_low", remaining=rem, delay=round(delay, 2))
        time.sleep(delay)


@retry(
    retry=retry_if_exception_type(AzureAPIError),
    stop=stop_after_attempt(_MAX_ATTEMPTS),
    wait=wait_exponential_jitter(initial=2, max=60),
    reraise=True,
)
def _request(method: str, url: str, headers: dict, params: dict = None,
             payload: dict = None) -> dict:
    """Single choke point for all ARM traffic: rate-limited, throttled, retried."""
    _wait_for_global_cooldown()
    patient = arm_patient_active()

    def _do_request() -> httpx.Response:
        try:
            return _get_http_client().request(
                method, url, headers=headers, params=params, json=payload,
            )
        except httpx.TimeoutException as exc:
            log.warning("arm_timeout", url=_short_url(url))
            raise AzureAPIError(504, "Timeout", str(exc)[:200]) from exc
        except httpx.HTTPError as exc:
            reset_http_client()
            log.debug("arm_connection_error", url=_short_url(url), error=str(exc)[:200])
            raise AzureAPIError(503, "ConnectionError", str(exc)[:200]) from exc

    if patient:
        with _patient_lock:
            resp = _do_request()
    else:
        _bucket.acquire()
        with _slots:
            resp = _do_request()
    if resp.status_code in _RETRYABLE_STATUS:
        retry_after = int(resp.headers.get("Retry-After", 0) or 0)
        log.warning(
            "arm_retryable",
            status=resp.status_code,
            retry_after=retry_after,
            url=_short_url(url),
        )
        if resp.status_code == 429:
            # Subscription read budget exhausted — pause *all* ARM callers.
            if retry_after > 0:
                pause = retry_after
            elif "Microsoft.CostManagement" in url:
                pause = _int_env("COST_429_COOLDOWN_SEC", 45)
            else:
                pause = 30
            _extend_global_cooldown(pause)
        else:
            sleep_secs = retry_after if retry_after > 0 else {502: 3, 503: 2, 504: 2}.get(resp.status_code, 1)
            time.sleep(sleep_secs)
        raise AzureAPIError(resp.status_code, "Retryable", resp.text[:200])
    _raise_for(resp)
    if not patient:
        _adaptive_throttle(resp)
    return resp.json()


def _get(url: str, headers: dict, params: dict = None, *, _retried: bool = False) -> dict:
    try:
        return _request("GET", url, headers, params=params)
    except AzureAPIError as exc:
        if exc.status == 401 and not _retried:
            from app.auth import auth_headers, current_arm_auth, reload_credential

            log.warning("arm_token_refresh", reason="401_from_azure")
            reload_credential()
            clear_cache()
            ctx = current_arm_auth()
            return _get(
                url,
                auth_headers(ctx.get("db")),
                params,
                _retried=True,
            )
        raise


def _post(url: str, headers: dict, payload: dict) -> dict:
    return _request("POST", url, headers, payload=payload)


def _patch(url: str, headers: dict, params: dict = None, payload: dict = None) -> dict:
    return _request("PATCH", url, headers, params=params, payload=payload)


def _cache_key(url: str, params: dict = None):
    return (url, tuple(sorted((params or {}).items())))


def get_all_pages(url: str, headers: dict, params: dict = None,
                  use_cache: bool = True) -> list:
    """Auto-paginate ARM list responses (following nextLink), with a short-TTL
    cache so repeated enumerations within the window don't re-hit ARM."""
    key = _cache_key(url, params)
    if use_cache and _CACHE_TTL > 0:
        with _cache_lock:
            hit = _cache_store.get(key)
            if hit and hit[0] > time.monotonic():
                return hit[1]

    results = []
    next_url = url
    while next_url:
        data = _get(next_url, headers, params if next_url == url else None)
        results.extend(data.get("value", []))
        next_url = data.get("nextLink")
        if next_url and _PAGE_DELAY_SEC and not arm_patient_active():
            time.sleep(_PAGE_DELAY_SEC)

    if use_cache and _CACHE_TTL > 0:
        with _cache_lock:
            _cache_store[key] = (time.monotonic() + _CACHE_TTL, results)
    return results


def clear_cache() -> None:
    """Drop all cached list results (e.g. after a credential/subscription change)."""
    with _cache_lock:
        _cache_store.clear()
