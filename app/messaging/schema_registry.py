"""JSON Schema loading, validation, and Redpanda Schema Registry integration."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
import yaml

from app.messaging.config import (
    kafka_schema_registry_enabled,
    kafka_schema_registry_url,
    kafka_schema_validation_enabled,
    resolve_repo_path,
)
from app.messaging.job_envelope import JobEnvelope

log = structlog.get_logger(__name__)

_SCHEMAS_ROOT = Path(__file__).resolve().parents[2] / "data" / "kafka" / "schemas"
_MANIFEST = _SCHEMAS_ROOT / "schemas-manifest.yaml"


@dataclass(frozen=True, slots=True)
class TopicSchemaBinding:
    topic: str
    subject: str
    schema_path: Path
    job_type: str
    payload_schema_path: Path | None
    producers: tuple[str, ...]
    consumers: tuple[str, ...]


def schemas_root() -> Path:
    return resolve_repo_path(
        os.getenv("KAFKA_SCHEMAS_DIR", ""),
        default=_SCHEMAS_ROOT,
    )


def manifest_path() -> Path:
    return resolve_repo_path(
        os.getenv("KAFKA_SCHEMAS_MANIFEST", ""),
        default=schemas_root() / "schemas-manifest.yaml",
    )


def subject_for_topic(topic: str) -> str:
    return f"{topic}-value"


@lru_cache(maxsize=1)
def load_schema_manifest() -> dict[str, Any]:
    path = manifest_path()
    if not path.is_file():
        raise FileNotFoundError(f"Schema manifest not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid schema manifest: {path}")
    return data


def topic_schema_bindings() -> dict[str, TopicSchemaBinding]:
    manifest = load_schema_manifest()
    topics = manifest.get("topics") or {}
    root = schemas_root()
    bindings: dict[str, TopicSchemaBinding] = {}

    for topic, raw in topics.items():
        if not isinstance(raw, dict):
            continue
        schema_rel = str(raw.get("schema_file", ""))
        payload_rel = raw.get("payload_schema")
        bindings[str(topic)] = TopicSchemaBinding(
            topic=str(topic),
            subject=str(raw.get("subject", subject_for_topic(str(topic)))),
            schema_path=root / schema_rel,
            job_type=str(raw.get("job_type", "")),
            payload_schema_path=(root / str(payload_rel)) if payload_rel else None,
            producers=tuple(str(p) for p in (raw.get("producers") or [])),
            consumers=tuple(str(c) for c in (raw.get("consumers") or [])),
        )

    return bindings


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_refs(node: Any, base_dir: Path) -> Any:
    """Inline local $ref for registry upload and jsonschema validation."""
    if isinstance(node, dict):
        if "$ref" in node and len(node) == 1:
            ref = node["$ref"]
            if isinstance(ref, str) and not ref.startswith("http"):
                target = (base_dir / ref).resolve()
                return _resolve_refs(_load_json(target), target.parent)
        return {key: _resolve_refs(value, base_dir) for key, value in node.items()}
    if isinstance(node, list):
        return [_resolve_refs(item, base_dir) for item in node]
    return node


@lru_cache(maxsize=32)
def resolved_schema_for_topic(topic: str) -> dict[str, Any]:
    binding = topic_schema_bindings().get(topic)
    if binding is None:
        raise KeyError(f"No schema binding for topic: {topic}")
    raw = _load_json(binding.schema_path)
    return _resolve_refs(raw, binding.schema_path.parent)


def _validator_for_topic(topic: str):
    try:
        import jsonschema
    except ImportError as exc:
        raise RuntimeError("jsonschema is required for schema validation") from exc

    schema = resolved_schema_for_topic(topic)
    return jsonschema.Draft202012Validator(schema)


def validate_envelope_dict(data: dict[str, Any], *, topic: str) -> None:
    if not kafka_schema_validation_enabled():
        return
    validator = _validator_for_topic(topic)
    validator.validate(data)


def validate_envelope(envelope: JobEnvelope, *, topic: str) -> None:
    if not kafka_schema_validation_enabled():
        return
    data = json.loads(envelope.to_json())
    validate_envelope_dict(data, topic=topic)


def serialize_envelope(envelope: JobEnvelope, *, topic: str) -> bytes:
    """Serialize envelope to UTF-8 JSON bytes, optionally validating first."""
    validate_envelope(envelope, topic=topic)
    return envelope.to_json().encode("utf-8")


def deserialize_envelope(raw: str | bytes | None, *, topic: str) -> JobEnvelope:
    """Deserialize envelope from Kafka message value (plain JSON, backward compatible)."""
    if raw is None:
        raise ValueError("Message value is empty")
    if isinstance(raw, bytes):
        text = raw.decode("utf-8")
    else:
        text = raw

    envelope = JobEnvelope.from_json(text)
    if kafka_schema_validation_enabled():
        try:
            validate_envelope(envelope, topic=topic)
        except Exception as exc:
            log.warning(
                "kafka.schema_validation_failed_on_consume",
                topic=topic,
                error=str(exc),
                hint="Message accepted for backward compatibility; fix producer or disable strict mode.",
            )
            if kafka_schema_validation_strict():
                raise
    return envelope


def kafka_schema_validation_strict() -> bool:
    return os.getenv("KAFKA_SCHEMA_VALIDATION_STRICT", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def envelope_to_registry_payload(topic: str) -> tuple[str, dict[str, Any]]:
    """Return (subject, resolved schema dict) for Schema Registry registration."""
    binding = topic_schema_bindings()[topic]
    return binding.subject, resolved_schema_for_topic(topic)


def register_schemas(*, registry_url: str | None = None, wait_sec: float = 60.0) -> int:
    """Register all topic schemas with Redpanda Schema Registry (REST API)."""
    if not kafka_schema_registry_enabled():
        log.info("schema_registry.register_skipped", reason="registry_disabled")
        return 0

    url_base = (registry_url or kafka_schema_registry_url()).rstrip("/")
    _wait_for_registry(url_base, wait_sec)

    registered = 0
    for topic in sorted(topic_schema_bindings()):
        subject, schema = envelope_to_registry_payload(topic)
        payload = json.dumps(
            {
                "schema": json.dumps(schema, separators=(",", ":"), sort_keys=True),
                "schemaType": "JSON",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{url_base}/subjects/{subject}/versions",
            data=payload,
            headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                registered += 1
                print(f"registered {subject} -> version {body.get('id')}")
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                print(f"schema unchanged: {subject}")
                registered += 1
            else:
                detail = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Failed to register {subject}: HTTP {exc.code} {detail}") from exc

    print(f"done: registered {registered} subjects at {url_base}")
    return registered


def verify_schemas_registered(*, registry_url: str | None = None) -> int:
    url_base = (registry_url or kafka_schema_registry_url()).rstrip("/")
    missing: list[str] = []
    for topic, binding in topic_schema_bindings().items():
        subject = binding.subject
        req = urllib.request.Request(
            f"{url_base}/subjects/{subject}/versions/latest",
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                if resp.status != 200:
                    missing.append(subject)
        except urllib.error.HTTPError:
            missing.append(subject)

    if missing:
        print("missing schema subjects:", ", ".join(sorted(missing)))
        return 1

    print(f"verified {len(topic_schema_bindings())} schema subjects at {url_base}")
    return 0


def _wait_for_registry(url_base: str, timeout_sec: float) -> None:
    import time

    deadline = time.monotonic() + timeout_sec
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(f"{url_base}/subjects", method="GET")
            with urllib.request.urlopen(req, timeout=5.0):
                return
        except Exception as exc:
            last_error = exc
            time.sleep(2.0)
    raise RuntimeError(f"Schema Registry not reachable at {url_base}: {last_error}")
