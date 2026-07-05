"""Normalize optimization finding evidence for API and UI consumption."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import json

from app.disk_staleness import augment_disk_evidence, is_disk_finding
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
    out.pop("_inventory_properties", None)
    out["evidence"] = evidence

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
        if isinstance(evidence, dict):
            evidence = dict(evidence)
            evidence["trigger_metrics"] = trigger_metrics
            out["evidence"] = evidence

    return out
