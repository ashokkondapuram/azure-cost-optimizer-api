"""Assessment JSON recommendations for indexed resources without dedicated sub-engines."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.analysis.orchestrator import row_to_arm_resource
from app.assessment.normalizer import resource_row_to_dict
from app.focus_mapping import normalize_arm_id
from app.optimizer.platform.runtime.base import ResourceSubEngine
from app.pipeline.store import indexed_resources_query, is_indexed_resource


class _AssessmentOnlyEvaluator(ResourceSubEngine):
    """Minimal sub-engine used only for assessment JSON rule evaluation."""

    component = "Assessment JSON"
    bucket_keys = ()

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        return []


def collect_covered_resource_ids(buckets: dict[str, list]) -> set[str]:
    """Normalized ARM ids already handled by per-resource sub-engines."""
    covered: set[str] = set()
    for rows in (buckets or {}).values():
        for row in rows or []:
            rid = normalize_arm_id(row.get("id") or row.get("resource_id") or "")
            if rid:
                covered.add(rid)
    return covered


def load_uncovered_indexed_resources(
    db: Session,
    subscription_id: str,
    covered_ids: set[str],
) -> list[dict[str, Any]]:
    """Load indexed inventory rows that are not routed through a sub-engine bucket."""
    resources: list[dict[str, Any]] = []
    for inv in indexed_resources_query(db, subscription_id):
        row_dict = resource_row_to_dict(inv)
        rid = normalize_arm_id(row_dict.get("resource_id") or "")
        if not rid or rid in covered_ids:
            continue
        if not is_indexed_resource(rid):
            continue
        arm_resource = row_to_arm_resource({
            "id": row_dict["resource_id"],
            "name": row_dict.get("resource_name") or "",
            "type": row_dict.get("canonical_type") or "",
            "location": row_dict.get("location") or "",
            "resourceGroup": row_dict.get("resource_group") or "",
            "tags": row_dict.get("tags") or {},
            "sku": row_dict.get("sku") or "",
            "properties": row_dict.get("properties") or {},
            "state": row_dict.get("state") or "",
        })
        arm_resource["_canonical_type"] = row_dict.get("canonical_type") or ""
        resources.append(arm_resource)
    return resources


def evaluate_assessment_recommendations(
    engine: Any,
    ctx: Any,
    resources: list[dict[str, Any]],
) -> list[Any]:
    """Evaluate assessment JSON rules for prepared inventory resources."""
    if not resources:
        return []
    evaluator = _AssessmentOnlyEvaluator(engine, ctx)
    prepared = evaluator.prepare_resources(resources)
    if not prepared:
        return []
    return evaluator.enhance_findings(
        evaluator.evaluate_assessment_findings(prepared),
        prepared,
    )


def run_uncovered_assessment_recommendations(
    db: Session,
    engine: Any,
    ctx: Any,
    buckets: dict[str, list],
) -> list[Any]:
    """Run assessment JSON rules for indexed resources missing a sub-engine bucket."""
    sub = (getattr(ctx, "subscription_id", None) or "").lower()
    if not sub:
        return []
    covered = collect_covered_resource_ids(buckets)
    uncovered = load_uncovered_indexed_resources(db, sub, covered)
    return evaluate_assessment_recommendations(engine, ctx, uncovered)
