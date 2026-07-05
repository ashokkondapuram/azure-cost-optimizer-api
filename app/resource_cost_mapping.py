"""Resource → cost-driving properties and metrics mapping."""

from __future__ import annotations

from typing import Any

from app.metrics_catalog import catalog_entry_from_metric, metrics_catalog_for_canonical_type
from app.metrics_triggers import METRIC_TRIGGERS, triggers_for_fact_key
from app.resources.registry import (
    ALL_RESOURCE_MODULES,
    TECHNICAL_FETCH_SPECS,
    get_technical_fetch_spec,
    profiles_for_canonical,
)


def _property_entry(field, *, canonical_type: str) -> dict[str, Any]:
    return {
        "kind": "property",
        "fact_key": field.fact_key,
        "label": field.label,
        "source": field.source,
        "category": field.category,
        "rules": list(field.rules),
        "canonical_type": canonical_type,
    }


def _metric_entry(metric_dict: dict[str, Any]) -> dict[str, Any]:
    trigger = triggers_for_fact_key(metric_dict.get("fact_key") or "")
    entry = {
        "kind": "metric",
        **metric_dict,
    }
    if trigger:
        entry["trigger"] = {
            "direction": trigger.direction,
            "threshold": trigger.threshold,
            "effect_cost": trigger.effect_cost,
            "effect_performance": trigger.effect_performance,
            "safety_gate": trigger.safety_gate or None,
        }
    return entry


def _cost_driver_sort_key(item: dict[str, Any]) -> tuple:
    kind_order = {"property": 0, "metric": 1, "cost_signal": 2}
    return (kind_order.get(item.get("kind"), 9), item.get("fact_key") or "")


def resource_cost_mapping_for_type(canonical_type: str) -> dict[str, Any]:
    """Properties, metrics, and merged cost drivers for one resource type."""
    ctype = (canonical_type or "").strip().lower()
    spec = get_technical_fetch_spec(ctype)

    properties = []
    if spec:
        properties = [
            _property_entry(f, canonical_type=ctype)
            for f in spec.fields
            if f.rules
        ]

    metrics_raw = metrics_catalog_for_canonical_type(ctype)
    cost_metrics = [
        _metric_entry(m)
        for m in metrics_raw
        if m.get("impact") in {"cost", "both"}
    ]

    cost_signals = [{
        "kind": "cost_signal",
        "fact_key": "monthly_cost_usd",
        "label": "Month-to-date cost",
        "source": "cost_export",
        "rules": _rules_for_fact("monthly_cost_usd"),
        "canonical_type": ctype,
    }]

    cost_drivers = sorted(
        [*properties, *cost_metrics, *cost_signals],
        key=_cost_driver_sort_key,
    )

    monitor_profiles = [
        {
            "monitor_arm_type": p.monitor_arm_type,
            "display_name": p.display_name,
            "metrics": [catalog_entry_from_metric(m, profile=p) for m in p.metrics],
        }
        for p in profiles_for_canonical(ctype)
    ]

    return {
        "canonical_type": ctype,
        "display_name": spec.display_name if spec else ctype,
        "arm_type": spec.arm_type if spec else None,
        "sync_property_paths": list(spec.sync_property_paths) if spec else [],
        "properties": properties,
        "metrics": cost_metrics,
        "cost_signals": cost_signals,
        "cost_drivers": cost_drivers,
        "monitor_profiles": monitor_profiles,
        "property_count": len(properties),
        "metric_count": len(cost_metrics),
    }


def _rules_for_fact(fact_key: str) -> list[str]:
    trigger = METRIC_TRIGGERS.get(fact_key)
    if trigger:
        return list(trigger.rules)
    rules: set[str] = set()
    for spec in TECHNICAL_FETCH_SPECS.values():
        for field in spec.fields:
            if field.fact_key == fact_key:
                rules.update(field.rules)
        for metric in spec.usage_metrics:
            if metric.fact_key == fact_key:
                rules.update(metric.rules)
    return sorted(rules)


def resource_cost_mapping(canonical_type: str | None = None) -> dict[str, Any]:
    """Full mapping or filter to one canonical type."""
    if canonical_type:
        entry = resource_cost_mapping_for_type(canonical_type)
        return {"count": 1, "resources": [entry]}

    types = sorted(
        {
            getattr(mod, "CANONICAL_TYPE", None)
            for mod in ALL_RESOURCE_MODULES
            if getattr(mod, "TECHNICAL_FETCH_SPEC", None) is not None
        }
        - {None}
    )
    resources = [resource_cost_mapping_for_type(t) for t in types]
    return {"count": len(resources), "resources": resources}


def cost_drivers_for_resource(
    resource_id: str,
    canonical_type: str | None = None,
) -> dict[str, Any]:
    """Cost drivers applicable to a specific ARM resource (by type + path rules)."""
    from app.resources.registry import monitor_arm_type
    from app.metrics_catalog import sql_server_metrics_unavailable

    unavailable = sql_server_metrics_unavailable(resource_id)
    if unavailable:
        return {
            "resource_id": resource_id,
            "canonical_type": canonical_type,
            **unavailable,
            "cost_drivers": [],
        }

    ctype = (canonical_type or "").strip().lower()
    if not ctype:
        from app.resource_type_map import internal_resource_type
        ctype = internal_resource_type(resource_id) or ""

    mapping = resource_cost_mapping_for_type(ctype) if ctype else {
        "canonical_type": ctype,
        "cost_drivers": [],
        "properties": [],
        "metrics": [],
    }

    arm_type = monitor_arm_type(resource_id)
    if arm_type == "microsoft.sql/servers/databases":
        mapping = resource_cost_mapping_for_type("database/sql")

    return {
        "resource_id": resource_id,
        "canonical_type": mapping.get("canonical_type"),
        "display_name": mapping.get("display_name"),
        "arm_type": mapping.get("arm_type"),
        "properties": mapping.get("properties", []),
        "metrics": mapping.get("metrics", []),
        "cost_drivers": mapping.get("cost_drivers", []),
        "sync_property_paths": mapping.get("sync_property_paths", []),
    }


def generate_resource_cost_mapping_markdown() -> str:
    """Human-readable resource → cost driver matrix."""
    data = resource_cost_mapping()
    lines = [
        "# Resource cost driver mapping",
        "",
        "Maps each resource type to inventory **properties** and Azure Monitor **metrics** that drive cost recommendations.",
        "",
        "Generated from `app/resource_cost_mapping.py`. Do not edit by hand.",
        "",
    ]
    for resource in data["resources"]:
        ctype = resource["canonical_type"]
        lines.append(f"## {resource.get('display_name') or ctype} (`{ctype}`)")
        if resource.get("arm_type"):
            lines.append(f"ARM type: `{resource['arm_type']}`")
        if resource.get("sync_property_paths"):
            paths = ", ".join(f"`{p}`" for p in resource["sync_property_paths"][:8])
            if len(resource["sync_property_paths"]) > 8:
                paths += ", …"
            lines.append(f"Synced properties: {paths}")
        lines.append("")

        if resource.get("properties"):
            lines.append("### Properties (inventory)")
            lines.append("")
            lines.append("| Fact | Label | Source | Rules |")
            lines.append("|------|-------|--------|-------|")
            for prop in resource["properties"]:
                rules = ", ".join(prop.get("rules") or []) or "—"
                lines.append(
                    f"| `{prop['fact_key']}` | {prop['label']} | `{prop['source']}` | {rules} |"
                )
            lines.append("")

        if resource.get("metrics"):
            lines.append("### Metrics (Azure Monitor / agent)")
            lines.append("")
            lines.append("| Fact | Azure metric | Impact | Rules | Cost effect |")
            lines.append("|------|--------------|--------|-------|-------------|")
            for metric in resource["metrics"]:
                rules = ", ".join(metric.get("rules") or []) or "—"
                effect = (metric.get("trigger") or {}).get("effect_cost") or "—"
                lines.append(
                    f"| `{metric['fact_key']}` | {metric.get('metric_name') or '—'} | "
                    f"{metric.get('impact') or '—'} | {rules} | {effect} |"
                )
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)
