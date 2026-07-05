"""Technical fact extraction from synced inventory rows."""

from __future__ import annotations

from typing import Any

from app.focus_mapping import normalize_arm_id
from app.resource_type_map import arm_provider_type, extract_rg_from_arm
from app.resources.computed import COMPUTED
from app.resources.registry import get_technical_fetch_spec
from app.resources.types import TechnicalFetchSpec, TechnicalFieldDef, get_nested, sku_text


def list_technical_fetch_specs() -> list[dict[str, Any]]:
    """Serialize all specs for API / documentation."""
    from app.arm_api_versions import ARM_GET_API_VERSIONS
    from app.arm_resource_enrichment import ENRICH_IF_EMPTY, ENRICH_IF_MISSING
    from app.resources.registry import TECHNICAL_FETCH_SPECS

    out: list[dict[str, Any]] = []
    for spec in sorted(TECHNICAL_FETCH_SPECS.values(), key=lambda s: s.canonical_type):
        arm_key = spec.arm_type.strip().lower()
        out.append({
            "canonical_type": spec.canonical_type,
            "arm_type": spec.arm_type,
            "display_name": spec.display_name,
            "generic_arm_sync": spec.generic_arm_sync,
            "arm_get_api_version": ARM_GET_API_VERSIONS.get(arm_key),
            "sync_property_paths": list(spec.sync_property_paths),
            "enrich_if_missing": list(spec.enrich_if_missing or ENRICH_IF_MISSING.get(spec.canonical_type, ())),
            "enrich_if_empty": list(spec.enrich_if_empty or ENRICH_IF_EMPTY.get(spec.canonical_type, ())),
            "technical_fields": [
                {
                    "fact_key": f.fact_key,
                    "source": f.source,
                    "label": f.label,
                    "category": f.category,
                    "rules": list(f.rules),
                }
                for f in spec.fields
            ],
            "usage_metrics": [
                {
                    "source": m.source,
                    "metric_name": m.metric_name,
                    "fact_key": m.fact_key,
                    "description": m.description,
                    "timespan": m.timespan,
                    "aggregation": m.aggregation,
                    "rules": list(m.rules),
                }
                for m in spec.usage_metrics
            ],
        })
    return out


def pick_sync_properties(arm_resource: dict[str, Any], spec: TechnicalFetchSpec | None) -> dict[str, Any]:
    """Extract ARM properties to persist in resource_snapshots.properties_json."""
    if not spec or not spec.sync_property_paths:
        props = (arm_resource.get("properties") or {}).copy()
        props.pop("source", None)
        return props

    src = arm_resource.get("properties") or {}
    out: dict[str, Any] = {}
    if spec.canonical_type == "compute/disk":
        from app.disk_staleness import normalize_disk_arm_properties
        return normalize_disk_arm_properties(arm_resource)
    if spec.canonical_type == "compute/snapshot":
        from app.resources.compute.snapshot import normalize_snapshot_arm_properties
        return normalize_snapshot_arm_properties(arm_resource)
    if spec.canonical_type == "storage/account":
        from app.resources.storage.account import normalize_storage_arm_properties
        return normalize_storage_arm_properties(arm_resource)
    for key in spec.sync_property_paths:
        val = src.get(key)
        if val is not None:
            out[key] = val
    return out


def _resolve_field_value(row: dict[str, Any], field_def: TechnicalFieldDef) -> Any:
    props = row.get("properties") or {}
    source = field_def.source

    if source.startswith("row:"):
        return row.get(source[4:])

    if source.startswith("sku:"):
        sku_details = row.get("skuDetails") or row.get("sku_json") or {}
        if isinstance(sku_details, str):
            try:
                import json
                sku_details = json.loads(sku_details)
            except Exception:
                sku_details = {}
        arm_sku = sku_details.get("arm") if isinstance(sku_details, dict) else {}
        if not isinstance(arm_sku, dict):
            arm_sku = {}
        return get_nested({"sku": arm_sku, **(sku_details if isinstance(sku_details, dict) else {})}, source[4:])

    if source.startswith("props:"):
        return get_nested(props, source[6:])

    if source.startswith("tag:"):
        tags = row.get("tags") or {}
        if isinstance(tags, dict):
            return tags.get(source[4:])
        return None

    if source.startswith("computed:"):
        fn = COMPUTED.get(source[9:])
        if fn:
            val = fn(row, props)
            if field_def.fact_key == "rule_count" and isinstance(val, list):
                return len(val)
            return val
        return None

    return None


def extract_technical_facts(
    row: dict[str, Any] | None,
    *,
    canonical_type: str | None = None,
) -> dict[str, Any]:
    """
    Build technical facts for usage and savings analysis from a resource row.
    Skips cost-export-only stubs without Azure inventory.
    """
    if not row:
        return {}

    props = dict(row.get("properties") or {})
    if props.get("source") == "cost_export" and len(props) <= 2:
        return {}

    canonical = (canonical_type or row.get("type") or "").strip().lower()
    spec = get_technical_fetch_spec(canonical)
    rid = normalize_arm_id(row.get("id") or "")
    arm_type = arm_provider_type(rid)
    rg = (row.get("resourceGroup") or "").strip() or extract_rg_from_arm(rid)

    facts: dict[str, Any] = {
        "data_source": "synced_inventory",
        "arm_resource_type": arm_type,
        "canonical_resource_type": canonical,
        "location": (row.get("location") or "").strip(),
        "resource_group": rg,
        "state": (row.get("state") or "").strip(),
    }

    sku_text_val = sku_text(row.get("sku"))
    sku_details = row.get("skuDetails") or row.get("sku_json") or {}
    if isinstance(sku_details, dict):
        if sku_details.get("catalog"):
            facts["sku_catalog"] = sku_details["catalog"]
        if sku_details.get("vm_size"):
            facts.setdefault("vm_size", sku_details["vm_size"])
        if sku_details.get("node_pools"):
            facts["node_pools"] = sku_details["node_pools"]
    if not sku_text_val and props.get("sku"):
        sku_text_val = sku_text(props.get("sku"))
    if sku_text_val:
        facts["sku"] = sku_text_val

    if spec:
        for field_def in spec.fields:
            val = _resolve_field_value(row, field_def)
            if val is None or val == "":
                continue
            if isinstance(val, list) and field_def.fact_key not in ("rule_count",):
                continue
            facts.setdefault(field_def.fact_key, val)
    else:
        if props.get("provisioningState"):
            facts["provisioning_state"] = props["provisioningState"]

    facts.pop("azure_service_name", None)
    facts.pop("billing_service_name", None)
    facts.pop("billingServiceName", None)

    return {k: v for k, v in facts.items() if v not in (None, "")}
