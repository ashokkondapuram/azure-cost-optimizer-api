"""Split and reassemble large data-pipeline payloads for Kafka size limits."""

from __future__ import annotations

import json
import threading
import uuid
from typing import Any

import structlog

from app.messaging.config import kafka_chunk_target_bytes
from app.messaging.job_envelope import JobEnvelope
from app.messaging.json_serialization import json_default, sanitize_for_json

log = structlog.get_logger(__name__)

# Sections that are commonly large and safe to split across chunks.
_CHUNKABLE_LIST_SECTIONS = frozenset(
    {"inventory_batches", "metrics_records", "daily_export_rows"}
)
_CHUNKABLE_DICT_SECTIONS = frozenset(
    {"cost_by_resource", "cost_by_service", "cost_by_resource_type"}
)


def estimate_json_bytes(value: Any) -> int:
    """Return UTF-8 byte length of a JSON serialization."""
    return len(
        json.dumps(
            sanitize_for_json(value),
            separators=(",", ":"),
            sort_keys=True,
            default=json_default,
        ).encode("utf-8")
    )


def _estimate_data_envelope_bytes(data: dict[str, Any], run_params: dict[str, Any] | None) -> int:
    payload = {"data": data, "run_params": dict(run_params or {})}
    return estimate_json_bytes(payload)


def _split_dict_items(
    name: str,
    data: dict[str, Any],
    *,
    stage: str,
    target_bytes: int,
    run_params: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Split a large mapping section into multiple partial section dicts."""
    if not data:
        return [{"stage": stage, "sections": {name: {}}, "summary": {}}]

    parts: list[dict[str, Any]] = []
    current: dict[str, Any] = {}
    for key, value in data.items():
        trial = dict(current)
        trial[key] = value
        trial_payload = {"stage": stage, "sections": {name: trial}, "summary": {}}
        if current and _estimate_data_envelope_bytes(trial_payload, run_params) > target_bytes:
            parts.append({"stage": stage, "sections": {name: current}, "summary": {}})
            current = {key: value}
        else:
            current = trial
    if current:
        parts.append({"stage": stage, "sections": {name: current}, "summary": {}})
    return parts


def _split_list_items(
    name: str,
    data: list[Any],
    *,
    stage: str,
    target_bytes: int,
    run_params: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Split a large list section into multiple partial section dicts."""
    if not data:
        return [{"stage": stage, "sections": {name: []}, "summary": {}}]

    parts: list[dict[str, Any]] = []
    current: list[Any] = []
    for item in data:
        trial = current + [item]
        trial_payload = {"stage": stage, "sections": {name: trial}, "summary": {}}
        if current and _estimate_data_envelope_bytes(trial_payload, run_params) > target_bytes:
            parts.append({"stage": stage, "sections": {name: current}, "summary": {}})
            current = [item]
        else:
            current = trial
    if current:
        parts.append({"stage": stage, "sections": {name: current}, "summary": {}})
    return parts


def _split_section(
    name: str,
    value: Any,
    *,
    stage: str,
    target_bytes: int,
    run_params: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if isinstance(value, dict) and name in _CHUNKABLE_DICT_SECTIONS:
        return _split_dict_items(name, value, stage=stage, target_bytes=target_bytes, run_params=run_params)
    if isinstance(value, list) and name in _CHUNKABLE_LIST_SECTIONS:
        return _split_list_items(name, value, stage=stage, target_bytes=target_bytes, run_params=run_params)

  # Fallback: emit as a single chunk even if oversized (broker limits may still apply).
    return [{"stage": stage, "sections": {name: value}, "summary": {}}]


def plan_data_chunks(
    data_payload: dict[str, Any],
    run_params: dict[str, Any] | None = None,
    *,
    target_bytes: int | None = None,
) -> list[dict[str, Any]]:
    """Plan one or more publishable data chunks for a stage payload.

    Returns a list of dicts shaped as ``{"data": ..., "chunk": ... optional}``.
    Unchunked payloads omit the ``chunk`` key for backward compatibility.
    """
    limit = target_bytes if target_bytes is not None else kafka_chunk_target_bytes()
    stage = str(data_payload.get("stage") or "")
    sections = dict(data_payload.get("sections") or {})
    summary = dict(data_payload.get("summary") or {})

    full = {"stage": stage, "sections": sections, "summary": summary}
    if _estimate_data_envelope_bytes(full, run_params) <= limit:
        return [{"data": full}]

    batch_id = str(uuid.uuid4())
    chunk_payloads: list[dict[str, Any]] = []
    small_sections: dict[str, Any] = {}

    for name, value in sections.items():
        partial = {name: value}
        partial_data = {"stage": stage, "sections": partial, "summary": {}}
        if _estimate_data_envelope_bytes(partial_data, run_params) <= limit:
            trial = dict(small_sections)
            trial[name] = value
            trial_data = {"stage": stage, "sections": trial, "summary": {}}
            if small_sections and _estimate_data_envelope_bytes(trial_data, run_params) > limit:
                chunk_payloads.append({"stage": stage, "sections": small_sections, "summary": {}})
                small_sections = {name: value}
            else:
                small_sections = trial
        else:
            if small_sections:
                chunk_payloads.append({"stage": stage, "sections": small_sections, "summary": {}})
                small_sections = {}
            chunk_payloads.extend(
                _split_section(
                    name,
                    value,
                    stage=stage,
                    target_bytes=limit,
                    run_params=run_params,
                )
            )

    if small_sections:
        chunk_payloads.append({"stage": stage, "sections": small_sections, "summary": {}})

    if not chunk_payloads:
        chunk_payloads = [full]

    if chunk_payloads:
        chunk_payloads[-1]["summary"] = summary

    total = len(chunk_payloads)
    if total == 1:
        return [{"data": chunk_payloads[0]}]

    planned: list[dict[str, Any]] = []
    for index, data in enumerate(chunk_payloads):
        planned.append(
            {
                "data": data,
                "chunk": {
                    "batch_id": batch_id,
                    "chunk_index": index,
                    "total_chunks": total,
                },
            }
        )
    log.info(
        "data_chunking.planned",
        stage=stage,
        total_chunks=total,
        batch_id=batch_id,
        section_count=len(sections),
    )
    return planned


def merge_chunked_data(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge chunked ``data`` payloads into a single stage payload."""
    if not chunks:
        return {}
    if len(chunks) == 1:
        return dict(chunks[0])

    merged: dict[str, Any] = {
        "stage": str(chunks[0].get("stage") or ""),
        "sections": {},
        "summary": {},
    }
    sections: dict[str, Any] = merged["sections"]

    for chunk in chunks:
        for name, value in (chunk.get("sections") or {}).items():
            if name not in sections:
                sections[name] = value
                continue
            existing = sections[name]
            if isinstance(existing, dict) and isinstance(value, dict):
                existing.update(value)
            elif isinstance(existing, list) and isinstance(value, list):
                existing.extend(value)
            else:
                sections[name] = value
        summary = chunk.get("summary") or {}
        if summary:
            merged["summary"].update(summary)

    return merged


class ChunkAssembler:
    """Buffer chunked data-topic messages until a full batch is received."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buffers: dict[str, dict[int, dict[str, Any]]] = {}
        self._totals: dict[str, int] = {}

    def reset(self) -> None:
        with self._lock:
            self._buffers.clear()
            self._totals.clear()

    def ingest(self, envelope: JobEnvelope) -> dict[str, Any] | None:
        """Return merged data when all chunks arrive; otherwise None."""
        payload = envelope.payload or {}
        chunk = payload.get("chunk")
        data = payload.get("data")
        if not isinstance(chunk, dict):
            return dict(data) if isinstance(data, dict) else {}

        batch_id = str(chunk.get("batch_id") or "")
        if not batch_id:
            return dict(data) if isinstance(data, dict) else {}

        try:
            chunk_index = int(chunk.get("chunk_index", 0))
            total_chunks = int(chunk.get("total_chunks", 1))
        except (TypeError, ValueError):
            return dict(data) if isinstance(data, dict) else {}

        if total_chunks <= 1:
            return dict(data) if isinstance(data, dict) else {}

        key = f"{envelope.pipeline_id}:{envelope.job_type.value}:{batch_id}"
        with self._lock:
            bucket = self._buffers.setdefault(key, {})
            bucket[chunk_index] = dict(data) if isinstance(data, dict) else {}
            self._totals[key] = total_chunks

            if len(bucket) < total_chunks:
                log.debug(
                    "data_chunking.buffered",
                    pipeline_id=envelope.pipeline_id,
                    batch_id=batch_id,
                    received=len(bucket),
                    total_chunks=total_chunks,
                )
                return None

            ordered = [bucket[i] for i in range(total_chunks)]
            del self._buffers[key]
            del self._totals[key]

        merged = merge_chunked_data(ordered)
        log.info(
            "data_chunking.reassembled",
            pipeline_id=envelope.pipeline_id,
            batch_id=batch_id,
            total_chunks=total_chunks,
            stage=merged.get("stage"),
        )
        return merged


_chunk_assembler = ChunkAssembler()


def get_chunk_assembler() -> ChunkAssembler:
    return _chunk_assembler
