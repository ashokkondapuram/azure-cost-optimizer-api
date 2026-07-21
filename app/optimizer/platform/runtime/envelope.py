"""Full resource envelope — configuration, associations, runtime metrics, and cost."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.cost_utils import resource_cost
from app.resource_type_map import internal_resource_type
from app.resources import (
    extract_technical_facts,
    get_technical_fetch_spec,
    get_technical_fetch_spec_by_arm,
    usage_metrics_for_canonical,
)

from .context import AnalysisContext


@dataclass
class ResourceEnvelope:
    resource: dict[str, Any]
    canonical_type: str
    facts: dict[str, Any]
    monthly_cost: float
    metrics: dict[str, Any] | None
    elements: dict[str, Any]

    def inject_into(self, resource: dict[str, Any]) -> dict[str, Any]:
        """Return a shallow copy with technical facts attached for rule evaluation."""
        out = dict(resource)
        out["_technical_facts"] = dict(self.facts)
        out["_resource_elements"] = dict(self.elements)
        out["_canonical_type"] = self.canonical_type
        return out


def resolve_canonical_type(resource: dict[str, Any]) -> str:
    rid = resource.get("id") or ""
    canonical = internal_resource_type(rid)
    if canonical:
        return canonical
    arm_type = (resource.get("type") or "").strip().lower()
    spec = get_technical_fetch_spec_by_arm(arm_type)
    if spec:
        return spec.canonical_type
    return arm_type


def build_resource_envelope(
    resource: dict[str, Any],
    ctx: AnalysisContext,
    *,
    metrics: dict[str, Any] | None = None,
) -> ResourceEnvelope:
    canonical = resolve_canonical_type(resource)
    facts = extract_technical_facts(resource, canonical_type=canonical)
    rid = (resource.get("id") or "").lower()
    monitor_facts = ctx.facts_for_resource(rid)
    if monitor_facts:
        facts.update(monitor_facts)
        facts["data_source"] = "azure_monitor"
    monthly = float(resource_cost(ctx.cost_by_resource, rid) or 0)
    props = resource.get("properties") or {}
    tags = resource.get("tags") or {}
    spec = get_technical_fetch_spec(canonical)

    configuration: dict[str, Any] = {
        "sku": facts.get("sku") or resource.get("sku"),
        "location": resource.get("location") or facts.get("location"),
        "state": resource.get("state") or facts.get("state"),
        "provisioning_state": facts.get("provisioning_state"),
    }
    if spec:
        for path in spec.sync_property_paths:
            val = _nested_get(props, path)
            if val not in (None, "", []):
                configuration[path.split(".")[-1]] = val

    associations = {
        k: facts[k]
        for k in facts
        if k in {
            "managed_by", "virtual_machine", "public_ip_address", "subnet_id",
            "server_farm_id", "backend_pool_count", "http_listener_count",
            "all_backends_empty", "attached_disk_count",
        }
    }

    runtime: dict[str, Any] = {}
    monitor_facts = ctx.facts_for_resource(rid)
    if metrics or monitor_facts:
        runtime["metrics_available"] = True
        for key, val in monitor_facts.items():
            runtime[key] = val
        profile_keys = {m.fact_key for m in usage_metrics_for_canonical(canonical)}
        for key in profile_keys:
            if key in facts:
                runtime[key] = facts[key]
    else:
        runtime["metrics_available"] = False

    elements = {
        "canonical_type": canonical,
        "arm_type": facts.get("arm_resource_type") or resource.get("type"),
        "configuration": {k: v for k, v in configuration.items() if v not in (None, "")},
        "associations": associations,
        "governance": {
            "tags": tags,
            "missing_required_tags": facts.get("missing_required_tags"),
        },
        "runtime": runtime,
        "cost": {
            "monthly_usd": round(monthly, 2),
        },
        "spec_field_count": len(spec.fields) if spec else 0,
    }

    return ResourceEnvelope(
        resource=resource,
        canonical_type=canonical,
        facts=facts,
        monthly_cost=monthly,
        metrics=metrics,
        elements=elements,
    )


def _nested_get(obj: dict[str, Any], path: str) -> Any:
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def merge_envelope_into_evidence(
    evidence: dict[str, Any],
    envelope: ResourceEnvelope | None,
) -> dict[str, Any]:
    if not envelope:
        return evidence
    merged = dict(evidence)
    merged.setdefault("exclude_inventory_facts", True)
    return merged
