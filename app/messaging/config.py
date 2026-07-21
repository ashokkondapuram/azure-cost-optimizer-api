"""Kafka configuration loaded from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve_repo_path(raw: str | Path, *, default: Path) -> Path:
    """Resolve *raw* against the repository root when it is a relative path."""
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return default
        path = Path(raw)
    else:
        path = raw
    if path.is_absolute():
        return path
    return _REPO_ROOT / path


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def kafka_enabled() -> bool:
    """Return True when Kafka pipeline dispatch is active."""
    return _env_bool("KAFKA_ENABLED", False)


def kafka_bootstrap_servers() -> str:
    return os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092").strip()


def kafka_client_id() -> str:
    return os.getenv("KAFKA_CLIENT_ID", "costoptimizer").strip() or "costoptimizer"


def kafka_consumer_group(service_id: str) -> str:
    prefix = os.getenv("KAFKA_CONSUMER_GROUP_PREFIX", "costoptimizer").strip() or "costoptimizer"
    return f"{prefix}.{service_id}"


def kafka_security_protocol() -> str:
    return os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT").strip() or "PLAINTEXT"


def kafka_auto_offset_reset() -> str:
    return os.getenv("KAFKA_AUTO_OFFSET_RESET", "earliest").strip() or "earliest"


def kafka_session_timeout_ms() -> int:
    return max(6000, int(os.getenv("KAFKA_SESSION_TIMEOUT_MS", "30000")))


def kafka_poll_timeout_sec() -> float:
    return max(0.1, float(os.getenv("KAFKA_POLL_TIMEOUT_SEC", "1.0")))


def kafka_connect_retry_delay_sec() -> float:
    return max(1.0, float(os.getenv("KAFKA_CONNECT_RETRY_DELAY_SEC", "5.0")))


def kafka_connect_retry_max_delay_sec() -> float:
    return max(5.0, float(os.getenv("KAFKA_CONNECT_RETRY_MAX_DELAY_SEC", "60.0")))


def kafka_topic_partitions() -> int:
    return max(1, int(os.getenv("KAFKA_TOPIC_PARTITIONS", "6")))


def kafka_topic_replication_factor() -> int:
    return max(1, int(os.getenv("KAFKA_TOPIC_REPLICATION_FACTOR", "1")))


def kafka_topic_retention_ms() -> int:
    return max(3_600_000, int(os.getenv("KAFKA_TOPIC_RETENTION_MS", "604800000")))


def kafka_topics_manifest_path() -> str:
    return os.getenv("KAFKA_TOPICS_MANIFEST", "/app/data/kafka-topics.yaml").strip()


def kafka_schema_registry_url() -> str:
    return os.getenv("KAFKA_SCHEMA_REGISTRY_URL", "http://127.0.0.1:18081").strip()


def kafka_schema_registry_enabled() -> bool:
    return _env_bool("KAFKA_SCHEMA_REGISTRY_ENABLED", True)


def kafka_schema_validation_enabled() -> bool:
    default = kafka_schema_registry_enabled()
    return _env_bool("KAFKA_SCHEMA_VALIDATION_ENABLED", default)


def kafka_schemas_manifest_path() -> str:
    return os.getenv("KAFKA_SCHEMAS_MANIFEST", "/app/data/kafka/schemas/schemas-manifest.yaml").strip()


def microservices_mode() -> bool:
    return _env_bool("MICROSERVICES_ONLY", False) or _env_bool("MICROSERVICES_ENABLED", False)


def kafka_pipeline_dispatch_enabled() -> bool:
    """Kafka dispatch is only used in microservices mode with KAFKA_ENABLED=true."""
    return kafka_enabled() and microservices_mode()


def kafka_data_pipeline_enabled() -> bool:
    """Route fetched sync data through Redpanda before PostgreSQL persist."""
    if not kafka_pipeline_dispatch_enabled():
        return False
    raw = os.getenv("KAFKA_DATA_PIPELINE_ENABLED")
    if raw is None:
        return True
    return _env_bool("KAFKA_DATA_PIPELINE_ENABLED", True)


def kafka_ensure_topics_on_startup() -> bool:
    return _env_bool("KAFKA_ENSURE_TOPICS_ON_STARTUP", True)


def kafka_message_max_bytes() -> int:
    """Broker/producer/consumer max message size (default 20 MiB for dev)."""
    return max(1_048_576, int(os.getenv("KAFKA_MESSAGE_MAX_BYTES", "20971520")))


def kafka_chunk_target_bytes() -> int:
    """Target max serialized data envelope size before chunking (default 750 KiB)."""
    default = min(768_000, kafka_message_max_bytes() // 2)
    return max(256_000, int(os.getenv("KAFKA_CHUNK_TARGET_BYTES", str(default))))


def kafka_publish_max_retries() -> int:
    """Number of publish retries after the initial attempt."""
    return max(0, int(os.getenv("KAFKA_PUBLISH_MAX_RETRIES", "3")))


def kafka_publish_retry_backoff_sec() -> float:
    """Base delay between publish retries (exponential backoff multiplier)."""
    return max(0.1, float(os.getenv("KAFKA_PUBLISH_RETRY_BACKOFF_SEC", "1.0")))


def kafka_publish_delivery_timeout_sec() -> float:
    """How long to wait for broker delivery acknowledgement per attempt."""
    return max(1.0, float(os.getenv("KAFKA_PUBLISH_DELIVERY_TIMEOUT_SEC", "10.0")))
