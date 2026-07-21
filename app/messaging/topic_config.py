"""Kafka topic manifest — partitions, retention, and service bindings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.messaging.config import kafka_consumer_group, resolve_repo_path

_DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parents[2] / "data" / "kafka-topics.yaml"


@dataclass(frozen=True, slots=True)
class TopicSpec:
    name: str
    partitions: int
    replication_factor: int
    retention_ms: int
    cleanup_policy: str
    compression_type: str
    producers: tuple[str, ...]
    consumers: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True, slots=True)
class ServiceTopicBinding:
    service_id: str
    consumes: tuple[str, ...]
    produces: tuple[str, ...]
    role: str = "worker"
    kafka_enabled: bool = True
    note: str = ""


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def default_partitions() -> int:
    return max(1, _env_int("KAFKA_TOPIC_PARTITIONS", 6))


def default_replication_factor() -> int:
    return max(1, _env_int("KAFKA_TOPIC_REPLICATION_FACTOR", 1))


def default_retention_ms() -> int:
    return max(3_600_000, _env_int("KAFKA_TOPIC_RETENTION_MS", 604_800_000))


def manifest_path() -> Path:
    return resolve_repo_path(
        os.getenv("KAFKA_TOPICS_MANIFEST", ""),
        default=_DEFAULT_MANIFEST_PATH,
    )


def _coerce_str_list(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, Any]:
    path = manifest_path()
    if not path.is_file():
        raise FileNotFoundError(f"Kafka topic manifest not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid Kafka topic manifest (expected mapping): {path}")
    return data


def topic_specs() -> tuple[TopicSpec, ...]:
    manifest = load_manifest()
    defaults = manifest.get("defaults") or {}
    topics = manifest.get("topics") or {}
    specs: list[TopicSpec] = []

    for name, raw in topics.items():
        if not isinstance(raw, dict):
            continue
        specs.append(
            TopicSpec(
                name=str(name),
                partitions=max(1, int(raw.get("partitions", defaults.get("partitions", default_partitions())))),
                replication_factor=max(
                    1,
                    int(raw.get("replication_factor", defaults.get("replication_factor", default_replication_factor()))),
                ),
                retention_ms=max(
                    3_600_000,
                    int(raw.get("retention_ms", defaults.get("retention_ms", default_retention_ms()))),
                ),
                cleanup_policy=str(raw.get("cleanup_policy", defaults.get("cleanup_policy", "delete"))),
                compression_type=str(raw.get("compression_type", defaults.get("compression_type", "producer"))),
                producers=_coerce_str_list(raw.get("producers")),
                consumers=_coerce_str_list(raw.get("consumers")),
                description=str(raw.get("description", "")),
            )
        )

    return tuple(sorted(specs, key=lambda spec: spec.name))


def topic_spec_map() -> dict[str, TopicSpec]:
    return {spec.name: spec for spec in topic_specs()}


def service_bindings() -> dict[str, ServiceTopicBinding]:
    manifest = load_manifest()
    services = manifest.get("services") or {}
    bindings: dict[str, ServiceTopicBinding] = {}

    for service_id, raw in services.items():
        if not isinstance(raw, dict):
            continue
        bindings[str(service_id)] = ServiceTopicBinding(
            service_id=str(service_id),
            consumes=_coerce_str_list(raw.get("consumes")),
            produces=_coerce_str_list(raw.get("produces")),
            role=str(raw.get("role", "worker")),
            kafka_enabled=bool(raw.get("kafka_enabled", True)),
            note=str(raw.get("note", "")),
        )

    return bindings


def consumer_topics_for_service(service_id: str) -> list[str]:
    binding = service_bindings().get(service_id)
    if binding is None or not binding.kafka_enabled:
        return []
    return list(binding.consumes)


def orchestration_topics_for_service(service_id: str) -> list[str]:
    return [topic for topic in consumer_topics_for_service(service_id) if topic.startswith("sync.")]


def data_topics_for_service(service_id: str) -> list[str]:
    return [topic for topic in consumer_topics_for_service(service_id) if topic.startswith("data.")]


def api_topics_for_service(service_id: str) -> list[str]:
    return [topic for topic in consumer_topics_for_service(service_id) if topic.startswith("api.")]


def producer_topics_for_service(service_id: str) -> list[str]:
    binding = service_bindings().get(service_id)
    if binding is None or not binding.kafka_enabled:
        return []
    return list(binding.produces)


def consumer_group_for_service(service_id: str) -> str:
    return kafka_consumer_group(service_id)


def data_consumer_group_for_service(service_id: str) -> str:
    return f"{kafka_consumer_group(service_id)}.data"


def all_sync_topic_names() -> tuple[str, ...]:
    return tuple(spec.name for spec in topic_specs())
