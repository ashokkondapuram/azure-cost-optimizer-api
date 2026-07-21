"""Normalize optimization finding evidence for API and UI consumption."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

import json

from app.disk_staleness import augment_disk_evidence, is_disk_finding
from app.assessment.governance_filter import internal_evidence_keys, strip_internal_evidence_keys
from app.focus_mapping import normalize_arm_id
from app.resource_page_registry import CANONICAL_TO_APP_ROUTE
from app.inventory_technical import arm_resource_type_for_finding
from app.models import ResourceSnapshot
from app.resources.types import sku_text
from app.rule_evidence_specs import apply_rule_evidence_spec

# ARM or canonical type → in-app resource list route
_RESOURCE_APP_ROUTES: dict[str, str] = {
    "microsoft.compute/virtualmachines": "/vms",
    "compute/vm": "/vms",
    "microsoft.compute/virtualmachinescalesets": "/vmss",
    "compute/vmss": "/vmss",
    "microsoft.compute/disks": "/disks",
    "compute/disk": "/disks",
    "microsoft.compute/snapshots": "/snapshots",
    "compute/snapshot": "/snapshots",
    "microsoft.containerservice/managedclusters": "/aks",
    "containers/aks": "/aks",
    "microsoft.containerregistry/registries": "/acr",
    "containers/acr": "/acr",
    "microsoft.web/sites": "/appservices",
    "appservice/webapp": "/appservices",
    "microsoft.storage/storageaccounts": "/storage",
    "storage/account": "/storage",
    "microsoft.network/publicipaddresses": "/publicips",
    "network/publicip": "/publicips",
    "microsoft.network/loadbalancers": "/loadbalancers",
    "network/loadbalancer": "/loadbalancers",
    "microsoft.network/applicationgateways": "/appgateways",
    "network/appgateway": "/appgateways",
    "microsoft.network/networksecuritygroups": "/nsgs",
    "network/nsg": "/nsgs",
    "microsoft.network/natgateways": "/natgateways",
    "network/nat": "/natgateways",
    "microsoft.network/privateendpoints": "/privateendpoints",
    "network/privateendpoint": "/privateendpoints",
    "microsoft.network/privatelinkservices": "/privatelinkservices",
    "network/privatelinkservice": "/privatelinkservices",
    "microsoft.network/privatednszones": "/privatedns",
    "network/privatedns": "/privatedns",
    "microsoft.network/networkinterfaces": "/nics",
    "network/nic": "/nics",
    "microsoft.sql/servers": "/sql",
    "database/sql": "/sql",
    "microsoft.documentdb/databaseaccounts": "/cosmosdb",
    "database/cosmosdb": "/cosmosdb",
    "microsoft.dbforpostgresql/flexibleservers": "/postgresql",
    "database/postgresql": "/postgresql",
    "microsoft.cache/redis": "/redis",
    "database/redis": "/redis",
    "microsoft.keyvault/vaults": "/keyvaults",
    "security/keyvault": "/keyvaults",
    "microsoft.operationalinsights/workspaces": "/loganalytics",
    "monitoring/loganalytics": "/loganalytics",
    "microsoft.insights/components": "/appinsights",
    "monitoring/appinsights": "/appinsights",
    "microsoft.apimanagement/service": "/apim",
    "integration/apim": "/apim",
    "microsoft.datafactory/factories": "/datafactory",
    "integration/datafactory": "/datafactory",
    "microsoft.logic/workflows": "/logicapps",
    "integration/logicapp": "/logicapps",
    "microsoft.eventhub/namespaces": "/eventhubs",
    "messaging/eventhub": "/eventhubs",
    "microsoft.servicebus/namespaces": "/servicebus",
    "messaging/servicebus": "/servicebus",
    "microsoft.databricks/workspaces": "/databricks",
    "analytics/databricks": "/databricks",
    "microsoft.synapse/workspaces": "/synapse",
    "analytics/synapse": "/synapse",
    "microsoft.kusto/clusters": "/adx",
    "analytics/adx": "/adx",
    "microsoft.machinelearningservices/workspaces": "/mlworkspace",
    "analytics/mlworkspace": "/mlworkspace",
    "microsoft.recoveryservices/vaults": "/recoveryvault",
    "backup/recoveryvault": "/recoveryvault",
    "microsoft.search/searchservices": "/cognitivesearch",
    "search/cognitivesearch": "/cognitivesearch",
    **{k: v for k, v in CANONICAL_TO_APP_ROUTE.items() if k not in (
        "monitoring/loganalytics", "monitoring/appinsights", "integration/apim",
        "integration/datafactory", "integration/logicapp", "messaging/eventhub",
        "messaging/servicebus", "analytics/databricks", "analytics/synapse",
        "analytics/adx", "analytics/mlworkspace", "backup/recoveryvault",
        "search/cognitivesearch",
    )},
}


def _norm_type(value: str) -> str:
    return (value or "").strip().lower()


def _arm_provider_from_id(resource_id: str) -> str:
    rid = (resource_id or "").lower()
    if "/providers/" not in rid:
        return ""
    parts = rid.split("/")
    try:
        idx = parts.index("providers")
        return f"{parts[idx + 1]}/{parts[idx + 2]}"
    except (ValueError, IndexError):
        return ""


def action_centre_href(resource_id: str, *, inspect: bool = False, section: str | None = None) -> str | None:
    """Deep link into the unified Action centre for a resource."""
    rid = normalize_arm_id(resource_id)
    if not rid or "/subscriptions/" not in rid.lower():
        return None
    params: dict[str, str] = {"resource": rid}
    if inspect:
        params["inspect"] = "1"
    if section:
        params["section"] = section
    return f"/action-centre?{urlencode(params)}"


def app_route_for_resource(resource_type: str, resource_id: str = "") -> str | None:
    for candidate in (_norm_type(resource_type), _arm_provider_from_id(resource_id)):
        if candidate and candidate in _RESOURCE_APP_ROUTES:
            return _RESOURCE_APP_ROUTES[candidate]
    rtype = _norm_type(resource_type)
    route = CANONICAL_TO_APP_ROUTE.get(rtype)
    if route:
        return route
    for prefix, fallback in (
        ("network/", "/publicips"),
        ("database/", "/sql"),
        ("compute/", "/vms"),
        ("containers/", "/aks"),
        ("appservice/", "/appservices"),
        ("storage/", "/storage"),
        ("security/", "/keyvaults"),
    ):
        if rtype.startswith(prefix):
            return fallback
    return None


def azure_portal_url(resource_id: str) -> str | None:
    rid = (resource_id or "").strip()
    if not rid or "/subscriptions/" not in rid.lower():
        return None
    if not rid.startswith("/"):
        rid = f"/{rid}"
    return f"https://portal.azure.com/#resource{quote(rid, safe='/')}"


def _sku_label(sku: Any) -> str:
    label = sku_text(sku)
    return label if label else "—"


def disk_inventory_properties_map(
    db: Any,
    subscription_id: str,
    resource_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Load synced disk properties keyed by normalized ARM id."""
    ids = {normalize_arm_id(rid) for rid in resource_ids if rid}
    if not db or not ids:
        return {}
    sub = (subscription_id or "").lower()
    rows = (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            ResourceSnapshot.resource_type == "compute/disk",
        )
        .all()
    )
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = normalize_arm_id(row.resource_id)
        if key not in ids:
            continue
        try:
            props = json.loads(row.properties_json or "{}")
        except Exception:
            props = {}
        if props:
            out[normalize_arm_id(row.resource_id)] = props
    return out


def build_rule_evidence(
    rule_id: str,
    facts: dict[str, Any] | None,
    *,
    finding: dict[str, Any] | None = None,
    estimated_savings_usd: float | None = None,
) -> dict[str, Any]:
    """Build full evidence payload from declarative rule spec + runtime facts."""
    finding = finding or {}
    payload = dict(facts or {})
    if is_disk_finding(finding):
        inv_props = finding.get("_inventory_properties")
        if isinstance(inv_props, dict):
            payload = augment_disk_evidence(payload, inv_props)
        elif isinstance(payload.get("properties"), dict):
            payload = augment_disk_evidence(payload, payload["properties"])
    else:
        from app.service_display import enrich_service_evidence_properties, resolve_canonical_type
        canonical = resolve_canonical_type(
            str(finding.get("resource_type") or payload.get("resource_type") or ""),
            rule_id,
        )
        inv_props = finding.get("_inventory_properties")
        props = inv_props if isinstance(inv_props, dict) else payload.get("properties")
        if isinstance(props, dict) and canonical != "generic":
            enriched_props = enrich_service_evidence_properties(canonical, props)
            payload.update(enriched_props)
            if enriched_props.get("sku_display") and not payload.get("sku_label"):
                payload["sku_label"] = enriched_props["sku_display"]
            if enriched_props.get("access_tier_display") and not payload.get("access_tier"):
                payload["access_tier"] = props.get("accessTier") or props.get("access_tier")
    enriched = apply_rule_evidence_spec(
        rule_id,
        payload,
        finding=finding,
        estimated_savings_usd=estimated_savings_usd,
    )
    if enriched.get("sku") and not enriched.get("sku_label"):
        enriched["sku_label"] = _sku_label(enriched["sku"])
    return enriched


def enrich_evidence(
    rule_id: str,
    evidence: dict[str, Any] | None,
    finding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return evidence with checks, summary, determination, and savings methodology."""
    finding = finding or {}
    estimated = finding.get("estimated_savings_usd")
    raw = evidence if isinstance(evidence, dict) else {}
    enriched = build_rule_evidence(
        rule_id,
        evidence,
        finding=finding,
        estimated_savings_usd=estimated,
    )
    for key in ("ai_insight", "rule_engine"):
        block = raw.get(key)
        if isinstance(block, dict) and block:
            enriched[key] = block
    return enriched


_API_EVIDENCE_STRIP_KEYS = internal_evidence_keys() | frozenset({
    "max_unattached_disk_days",
    "disk_io_idle_bps",
    "disk_idle_min_size_gb",
    "disk_iops_block_downgrade_pct",
    "disk_iops_high_util_pct",
    "disk_throughput_high_util_pct",
    "evaluation_window_days",
    "min_monthly_savings_usd",
    "disk_capacity_used_pct_max",
    "disk_queue_depth_contention",
    "api_type",
    "consistency_level",
    "serverless_enabled",
    "multi_write_enabled",
    "automatic_failover_enabled",
    "free_tier_enabled",
    "capabilities",
    "currentRegion",
    "recommendedRegion",
    "recommendedRegionDisplay",
    "regionClassification",
    "regionApproved",
    "regionMigrationRequired",
})


def sanitize_evidence_for_api(evidence: dict[str, Any] | None) -> dict[str, Any]:
    """Remove assessment/config metadata from API evidence payloads."""
    if not isinstance(evidence, dict):
        return {}
    cleaned = strip_internal_evidence_keys(evidence)
    cleaned = {key: value for key, value in cleaned.items() if key not in _API_EVIDENCE_STRIP_KEYS}
    cleaned.pop("_evidence_meta", None)
    return cleaned


def enrich_finding_for_api(
    finding: dict[str, Any],
    *,
    inventory_properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add structured evidence and navigation links to a finding payload."""
    out = dict(finding)
    rule_id = out.get("rule_id") or ""
    if is_disk_finding(out) and inventory_properties:
        out["_inventory_properties"] = inventory_properties
    evidence = enrich_evidence(rule_id, out.get("evidence"), out)
    if is_disk_finding(out) and not evidence.get("evidence_rows"):
        try:
            from it_services.compute_disk.assessment_bridge import augment_finding_evidence

            evidence = augment_finding_evidence(rule_id, evidence)
        except Exception:
            pass
    elif (rule_id or "").startswith("COSMOS_") and not evidence.get("evidence_rows"):
        try:
            from it_services.database_cosmosdb.assessment_bridge import augment_finding_evidence as augment_cosmos_evidence

            evidence = augment_cosmos_evidence(rule_id, evidence)
        except Exception:
            pass
    out.pop("_inventory_properties", None)
    sanitized_evidence = sanitize_evidence_for_api(evidence)
    out["evidence"] = sanitized_evidence

    resource_id = out.get("resource_id") or ""
    resource_type = arm_resource_type_for_finding(
        resource_id,
        out.get("resource_type") or "",
    )
    out["resource_type"] = resource_type
    resource_name = out.get("resource_name") or ""

    app_route = app_route_for_resource(resource_type, resource_id)
    if app_route:
        out["resource_app_path"] = app_route

    ac_href = action_centre_href(resource_id, inspect=True, section="advanced-analysis")
    if ac_href:
        out["resource_app_href"] = ac_href
    elif app_route:
        if resource_name:
            out["resource_app_href"] = f"{app_route}?search={quote(resource_name)}"
        else:
            out["resource_app_href"] = app_route

    portal = azure_portal_url(resource_id)
    if portal:
        out["azure_portal_url"] = portal

    from app.metrics_triggers import trigger_reason_for_finding
    trigger_metrics = trigger_reason_for_finding(rule_id, evidence or {})
    if trigger_metrics:
        out["trigger_metrics"] = trigger_metrics
        merged_evidence = dict(sanitized_evidence)
        merged_evidence["trigger_metrics"] = trigger_metrics
        out["evidence"] = merged_evidence

    from app.recommendation_output import enrich_recommendation_narrative
    narrative = enrich_recommendation_narrative(out)
    if narrative.get("narrative"):
        out["narrative"] = narrative["narrative"]
    if narrative.get("highlights"):
        out["narrative_highlights"] = narrative["highlights"]
    if narrative.get("action_text"):
        out["action_text"] = narrative["action_text"]

    from app.finding_taxonomy import format_category_label, format_severity_label
    out["category_label"] = format_category_label(out.get("category"))
    out["severity_label"] = format_severity_label(out.get("severity"))
    if out.get("azureServiceName"):
        out["azure_service_name"] = out["azureServiceName"]
    elif out.get("resource_type"):
        service = str(out.get("resource_type") or "").replace("/", " · ")
        if service:
            out["azure_service_name"] = service

    return out
