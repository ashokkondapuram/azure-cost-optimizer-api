"""Kafka topic provisioning via confluent-kafka Admin API."""

from __future__ import annotations

import time


def _admin_client(brokers: str):
    try:
        from confluent_kafka.admin import AdminClient
    except ImportError as exc:
        raise RuntimeError(
            "confluent-kafka is required. Install requirements.txt or run inside python-base."
        ) from exc

    return AdminClient(
        {
            "bootstrap.servers": brokers,
            "security.protocol": "PLAINTEXT",
        }
    )


def wait_for_broker(brokers: str, timeout_sec: float) -> None:
    deadline = time.monotonic() + timeout_sec
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            admin = _admin_client(brokers)
            metadata = admin.list_topics(timeout=5.0)
            if metadata is not None:
                return
        except Exception as exc:
            last_error = exc
            time.sleep(2.0)
    raise RuntimeError(f"Broker not reachable at {brokers}: {last_error}")


def _topic_needs_large_message_bytes(topic_name: str) -> bool:
    """Topics that may carry large Azure API payloads need broker max.message.bytes."""
    if topic_name.startswith("data."):
        return True
    if topic_name == "api.dead-letter":
        return True
    if topic_name.startswith("api.") and topic_name.endswith(".completed"):
        return True
    return False


def provision_topics(*, brokers: str, wait_sec: float) -> int:
    from confluent_kafka.admin import ConfigResource, NewTopic

    from app.messaging.config import kafka_message_max_bytes
    from app.messaging.topic_config import topic_specs

    wait_for_broker(brokers, wait_sec)
    admin = _admin_client(brokers)
    existing = set(admin.list_topics(timeout=10.0).topics.keys())

    max_message_bytes = str(kafka_message_max_bytes())
    created = 0
    altered = 0
    for spec in topic_specs():
        config = {
            "retention.ms": str(spec.retention_ms),
            "cleanup.policy": spec.cleanup_policy,
            "compression.type": spec.compression_type,
        }
        if _topic_needs_large_message_bytes(spec.name):
            config["max.message.bytes"] = max_message_bytes
        if spec.name in existing:
            try:
                resource = ConfigResource("topic", spec.name)
                futures = admin.alter_configs({resource: config})
                for future in futures.values():
                    future.result(timeout=15.0)
                altered += 1
            except Exception:
                pass
            continue

        new_topic = NewTopic(
            spec.name,
            num_partitions=spec.partitions,
            replication_factor=spec.replication_factor,
            config=config,
        )
        futures = admin.create_topics([new_topic], request_timeout=30.0)
        for topic_name, future in futures.items():
            try:
                future.result(timeout=30.0)
                created += 1
            except Exception as exc:
                if "TOPIC_ALREADY_EXISTS" not in str(exc):
                    raise

    return created + altered


def verify_topics(*, brokers: str, wait_sec: float) -> int:
    from app.messaging.topic_config import topic_spec_map

    wait_for_broker(brokers, wait_sec)
    admin = _admin_client(brokers)
    metadata = admin.list_topics(timeout=10.0)
    existing = metadata.topics
    expected = topic_spec_map()
    missing: list[str] = []
    mismatched: list[str] = []

    for name, spec in expected.items():
        if name not in existing:
            missing.append(name)
            continue
        topic_meta = existing[name]
        if topic_meta.error is not None:
            missing.append(name)
            continue
        partition_count = len(topic_meta.partitions)
        if partition_count < spec.partitions:
            mismatched.append(f"{name}: partitions={partition_count} expected>={spec.partitions}")

    if missing or mismatched:
        return 1
    return 0
