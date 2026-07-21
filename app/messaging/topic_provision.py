"""Ensure Kafka topics exist before producers/consumers start."""

from __future__ import annotations

import structlog

from app.messaging.config import kafka_bootstrap_servers, kafka_enabled

log = structlog.get_logger(__name__)

_provisioned = False


def ensure_topics_provisioned(*, wait_sec: float = 30.0) -> bool:
    """Create topics from manifest if missing. Safe to call repeatedly."""
    global _provisioned
    if _provisioned:
        return True
    if not kafka_enabled():
        return False

    try:
        from app.messaging.topic_admin import provision_topics

        provision_topics(brokers=kafka_bootstrap_servers(), wait_sec=wait_sec)
        _provisioned = True
        log.info("kafka.topics_provisioned", brokers=kafka_bootstrap_servers())
        return True
    except Exception:
        log.exception(
            "kafka.topics_provision_failed",
            brokers=kafka_bootstrap_servers(),
            hint="Consumers will retry until topics exist.",
        )
        return False


def ensure_schemas_registered(*, wait_sec: float = 30.0) -> bool:
    """Register JSON schemas with Schema Registry (best-effort)."""
    try:
        from app.messaging.config import kafka_schema_registry_enabled
        from app.messaging.schema_registry import register_schemas

        if not kafka_schema_registry_enabled():
            return False
        register_schemas(wait_sec=wait_sec)
        return True
    except Exception:
        log.exception("kafka.schemas_register_failed")
        return False
