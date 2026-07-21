"""Data quality worker — scores resources using assessment JSON pythonAssessment."""

from __future__ import annotations

import json
import os
import uuid
import structlog
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.assessment.catalog import get_assessment_for_arm_type
from app.assessment.normalizer import build_normalized_record, resource_row_to_dict
from app.assessment.runtime import assess_data_quality, evaluate_assessment_rules
from app.assessment.signals import compute_signals
from app.assessment.spec import assessment_metadata, required_metric_keys, required_normalized_input
from it_services.sku_specs import load_sku_specs_for_canonical, sku_summary
from app.models import ResourceAssessmentResult, ResourceSnapshot
from app.pipeline.store import get_or_create_snapshot, is_indexed_resource, iter_pipeline_enrichment_rows, load_snapshot_dict

log = structlog.get_logger(__name__)


def data_quality_worker_enabled() -> bool:
    return os.getenv("DATA_QUALITY_WORKER_ENABLED", "true").lower() not in {"0", "false", "no"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _missing_normalized_fields(record: dict[str, Any], required_fields: list[str]) -> list[str]:
    missing: list[str] = []
    for field in required_fields:
        root = field.split(".", 1)[0]
        if root in {"resource", "properties", "metrics", "cost", "tags", "policy", "signals"}:
            if not record.get(root):
                missing.append(field)
        elif field == "resource_id" and not record.get("resource_id"):
            missing.append(field)
        elif field == "resource_type" and not record.get("resource_type"):
            missing.append(field)
    return missing


def _assessment_result_row(
    db: Session,
    *,
    subscription_id: str,
    resource_id: str,
    resource_type: str,
    assessment_file: str | None,
    quality: dict[str, Any],
    investigate_rules: list[dict[str, Any]],
) -> ResourceAssessmentResult:
    sub = subscription_id.lower()
    row = (
        db.query(ResourceAssessmentResult)
        .filter(
            ResourceAssessmentResult.subscription_id == sub,
            ResourceAssessmentResult.resource_id == resource_id,
        )
        .first()
    )
    payload = {
        **quality,
        "matchedInvestigateRules": [
            {"id": r.get("id"), "pillar": r.get("pillar"), "severity": r.get("severity")}
            for r in investigate_rules
        ],
    }
    if row:
        row.assessment_file = assessment_file
        row.score = float(quality.get("score") or 0)
        row.classification = quality.get("classification") or "unknown"
        row.data_quality_json = json.dumps(payload)
        row.assessed_at = _now()
        return row

    row = ResourceAssessmentResult(
        id=str(uuid.uuid4()),
        subscription_id=sub,
        resource_id=resource_id,
        resource_type=resource_type,
        assessment_file=assessment_file,
        score=float(quality.get("score") or 0),
        classification=quality.get("classification") or "unknown",
        data_quality_json=json.dumps(payload),
        assessed_at=_now(),
    )
    db.add(row)
    return row


def run_data_quality_worker(db: Session, subscription_id: str) -> dict[str, Any]:
    """Evaluate data quality from assessment JSON pythonAssessment for indexed resources."""
    sub = subscription_id.lower()
    stats: dict[str, Any] = {
        "subscription_id": sub,
        "assessed": 0,
        "skipped_no_assessment": 0,
        "skipped_not_indexed": 0,
        "assessment_files": [],
    }

    if not data_quality_worker_enabled():
        stats["status"] = "disabled"
        return stats

    snapshot_by_rid = {
        (row.arm_id or "").lower(): row
        for row in iter_pipeline_enrichment_rows(db, sub)
    }
    assessment_files: set[str] = set()

    inventory = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.is_active.is_(True),
        )
        .all()
    )

    for inv in inventory:
        row_dict = resource_row_to_dict(inv)
        if not is_indexed_resource(row_dict["resource_id"]):
            stats["skipped_not_indexed"] += 1
            continue

        arm_type = row_dict.get("resource_type") or ""
        assessment = get_assessment_for_arm_type(arm_type)
        if not assessment:
            stats["skipped_no_assessment"] += 1
            continue

        assessment_ref = assessment_metadata(assessment)
        assessment_files.add(assessment_ref.get("assessment_file") or "")

        snap = snapshot_by_rid.get(row_dict["resource_id"].lower())
        snap_data = load_snapshot_dict(snap) if snap else {}
        metrics = snap_data.get("metrics") or {}
        metric_keys = required_metric_keys(assessment)

        record = build_normalized_record(
            row_dict,
            metrics=metrics,
            required_metric_keys=metric_keys or None,
        )
        record["signals"] = compute_signals(record, required_metric_keys=metric_keys or None)
        if snap_data:
            record = {
                **snap_data,
                **record,
                "metrics": record.get("metrics"),
                "cost": record.get("cost"),
                "signals": record["signals"],
            }
        record["assessment"] = assessment_ref
        sku_spec = load_sku_specs_for_canonical(row_dict.get("canonical_type") or "")
        if sku_spec:
            record["sku_specs"] = sku_spec
            record["sku_summary"] = sku_summary(sku_spec)

        missing_fields = _missing_normalized_fields(
            record,
            required_normalized_input(assessment),
        )
        if missing_fields:
            record["signals"]["missingNormalizedInput"] = True
            record["signals"]["missingNormalizedFields"] = missing_fields

        quality = assess_data_quality(assessment, record)
        quality["assessment_file"] = assessment.get("_file")
        quality["required_metric_keys"] = metric_keys
        if missing_fields:
            quality["missing_normalized_input"] = missing_fields

        investigate_rules = evaluate_assessment_rules(
            assessment,
            record,
            rule_filter="data_quality",
        )

        _assessment_result_row(
            db,
            subscription_id=sub,
            resource_id=row_dict["resource_id"],
            resource_type=arm_type,
            assessment_file=assessment.get("_file"),
            quality=quality,
            investigate_rules=investigate_rules,
        )

        snap_row = get_or_create_snapshot(
            db,
            subscription_id=sub,
            resource_id=row_dict["resource_id"],
            resource_type=arm_type,
            canonical_type=row_dict.get("canonical_type"),
        )
        merged = dict(load_snapshot_dict(snap_row))
        merged.update({
            "resource_id": record.get("resource_id"),
            "resource_type": record.get("resource_type"),
            "resource": record.get("resource"),
            "properties": record.get("properties"),
            "metrics": record.get("metrics"),
            "cost": record.get("cost"),
            "tags": record.get("tags"),
            "policy": record.get("policy"),
            "signals": record.get("signals"),
            "assessment": record.get("assessment"),
            "sku_specs": record.get("sku_specs"),
            "sku_summary": record.get("sku_summary"),
        })
        snap_row.snapshot_json = json.dumps(merged)
        snap_row.cost_at = _now()
        snap_row.pipeline_stage = "quality_scored"
        snap_row.updated_at = _now()
        stats["assessed"] += 1

    db.commit()
    stats["assessment_files"] = sorted(f for f in assessment_files if f)
    stats["status"] = "ok"
    stats["completed_at"] = _now().isoformat()
    log.info("data_quality_worker.done", **stats)
    return stats
