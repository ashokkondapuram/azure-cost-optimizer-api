"""Environment configuration for Kafka API throttling."""

from __future__ import annotations

import os

from app.messaging.config import kafka_pipeline_dispatch_enabled


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return max(minimum, default)


def _env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return max(minimum, default)


def kafka_api_throttle_enabled() -> bool:
    """True when sync stages fan out Azure calls through api.* Kafka topics."""
    if not kafka_pipeline_dispatch_enabled():
        return False
    return _env_bool("KAFKA_API_THROTTLE_ENABLED", False)


def kafka_api_dlq_enabled() -> bool:
    return _env_bool("KAFKA_API_DLQ_ENABLED", True)


def api_cost_rate_per_sec() -> float:
    for name in ("KAFKA_API_COST_RATE_PER_SEC", "API_COST_RPS"):
        raw = os.getenv(name, "").strip()
        if raw:
            return _env_float(name, 0.1, minimum=0.1)
    return 0.1


def api_cost_burst() -> int:
    for name in ("KAFKA_API_COST_BURST", "API_COST_BURST"):
        if os.getenv(name, "").strip():
            return _env_int(name, 1)
    return 1


def api_cost_worker_concurrency() -> int:
    return _env_int("KAFKA_API_COST_WORKER_CONCURRENCY", 3)


def api_metrics_rate_per_sec() -> float:
    for name in ("KAFKA_API_METRICS_RATE_PER_SEC", "API_MONITOR_RPS"):
        raw = os.getenv(name, "").strip()
        if raw:
            return _env_float(name, 4.0, minimum=0.1)
    return 4.0


def api_metrics_burst() -> int:
    for name in ("KAFKA_API_METRICS_BURST", "API_MONITOR_BURST"):
        if os.getenv(name, "").strip():
            return _env_int(name, 4)
    return 4


def api_metrics_worker_concurrency() -> int:
    return _env_int("KAFKA_API_METRICS_WORKER_CONCURRENCY", 3)


def api_inventory_rate_per_sec() -> float:
    for name in ("KAFKA_API_INVENTORY_RATE_PER_SEC", "API_RESOURCE_GRAPH_RPS"):
        raw = os.getenv(name, "").strip()
        if raw:
            return _env_float(name, 4.0, minimum=0.1)
    return 4.0


def api_inventory_burst() -> int:
    for name in ("KAFKA_API_INVENTORY_BURST", "API_RESOURCE_GRAPH_BURST"):
        if os.getenv(name, "").strip():
            return _env_int(name, 4)
    return 4


def api_inventory_worker_concurrency() -> int:
    return _env_int("KAFKA_API_INVENTORY_WORKER_CONCURRENCY", 4)


def api_worker_poll_timeout_sec() -> float:
    return _env_float("KAFKA_API_WORKER_POLL_TIMEOUT_SEC", 1.0, minimum=0.1)


def api_aggregate_timeout_sec() -> float:
    return _env_float("KAFKA_API_AGGREGATE_TIMEOUT_SEC", 900.0, minimum=30.0)


def api_consumer_group_suffix(api_kind: str) -> str:
    """Suffix for dedicated worker-pool consumer groups."""
    return f"api.{api_kind}"


def api_aggregate_consumer_group_suffix(api_kind: str) -> str:
    return f"api.{api_kind}.aggregate"


def api_throttle_max_retries() -> int:
    for name in ("KAFKA_API_THROTTLE_MAX_RETRIES", "API_THROTTLE_MAX_RETRIES"):
        raw = os.getenv(name, "").strip()
        if raw:
            return _env_int(name, 3, minimum=0)
    return 3


def api_throttle_retry_delay_sec() -> float:
    for name in ("KAFKA_API_THROTTLE_RETRY_DELAY_SEC", "API_THROTTLE_RETRY_DELAY_SEC"):
        raw = os.getenv(name, "").strip()
        if raw:
            return _env_float(name, 15.0, minimum=1.0)
    return 15.0


def api_throttle_consumer_lag_threshold() -> int:
    for name in ("KAFKA_API_THROTTLE_LAG_THRESHOLD", "API_THROTTLE_CONSUMER_LAG_THRESHOLD"):
        raw = os.getenv(name, "").strip()
        if raw:
            return _env_int(name, 50, minimum=1)
    return 50


def api_throttle_wait_timeout_sec() -> float:
    for name in ("KAFKA_API_THROTTLE_WAIT_TIMEOUT_SEC", "API_THROTTLE_WAIT_TIMEOUT_SEC"):
        raw = os.getenv(name, "").strip()
        if raw:
            return _env_float(name, 120.0, minimum=5.0)
    return 120.0


def api_rps_for_domain(domain) -> float:
    from app.messaging.api_throttle.envelope import ApiDomain

    mapping = {
        ApiDomain.COST_MANAGEMENT: api_cost_rate_per_sec(),
        ApiDomain.MONITOR: api_metrics_rate_per_sec(),
        ApiDomain.RESOURCE_GRAPH: api_inventory_rate_per_sec(),
    }
    return mapping.get(domain, 2.0)


def api_burst_for_domain(domain) -> float:
    from app.messaging.api_throttle.envelope import ApiDomain

    mapping = {
        ApiDomain.COST_MANAGEMENT: float(api_cost_burst()),
        ApiDomain.MONITOR: float(api_metrics_burst()),
        ApiDomain.RESOURCE_GRAPH: float(api_inventory_burst()),
    }
    return mapping.get(domain, 4.0)


def api_query_delay_sec_for_domain(domain) -> float:
    from app.messaging.api_throttle.envelope import ApiDomain

    if domain == ApiDomain.COST_MANAGEMENT:
        return _env_float("COST_QUERY_DELAY_SEC", 0.0, minimum=0.0)
    if domain == ApiDomain.MONITOR:
        return _env_float("SYNC_MONITOR_METRICS_TIMEOUT_SEC", 0.0, minimum=0.0) / 30.0
    return 0.0
