"""Human-readable labels and evidence formatting for all Azure IT services."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.resources.types import format_fact_display_value, sku_text
from app.storage_account_catalog import (
    access_tier_spec,
    optimization_thresholds as storage_optimization_thresholds,
    recommendation_text as storage_recommendation_text,
    replication_display_name,
)

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULTS_PATH = _ROOT / "data" / "service_display_defaults.json"
_GB = 1024**3

CANONICAL_THRESHOLDS_PATHS: dict[str, str] = {
    "compute/vm": "data/vm-assessment.json",
    "compute/vmss": "data/vmss-assessment.json",
    "compute/disk": "data/disk-assessment.json",
    "database/cosmosdb": "data/cosmosdb-assessment.json",
    "storage/account": "data/storage_account_metrics_thresholds.json",
    "containers/aks": "data/aks_cluster_metrics_thresholds.json",
    "network/loadbalancer": "data/load_balancer_metrics_thresholds.json",
    "network/appgateway": "data/app_gateway_metrics_thresholds.json",
    "network/publicip": "data/public_ip_metrics_thresholds.json",
    "network/nat": "data/nat_gateway_metrics_thresholds.json",
    "analytics/databricks": "data/databricks_metrics_thresholds.json",
    "analytics/synapse": "data/synapse_metrics_thresholds.json",
    "analytics/adx": "data/adx_metrics_thresholds.json",
    "analytics/mlworkspace": "data/mlworkspace_metrics_thresholds.json",
    "integration/apim": "data/apim_metrics_thresholds.json",
    "integration/datafactory": "data/datafactory_metrics_thresholds.json",
    "integration/logicapp": "data/logicapp_metrics_thresholds.json",
    "messaging/eventhub": "data/eventhub_metrics_thresholds.json",
    "messaging/servicebus": "data/servicebus_metrics_thresholds.json",
    "monitoring/loganalytics": "data/loganalytics_metrics_thresholds.json",
    "monitoring/appinsights": "data/appinsights_metrics_thresholds.json",
    "backup/recoveryvault": "data/recoveryvault_metrics_thresholds.json",
    "search/cognitivesearch": "data/cognitivesearch_metrics_thresholds.json",
    "network/frontdoor": "data/frontdoor_metrics_thresholds.json",
}

_ARM_TO_CANONICAL: dict[str, str] = {
    "microsoft.compute/virtualmachines": "compute/vm",
    "microsoft.compute/virtualmachinescalesets": "compute/vmss",
    "microsoft.compute/disks": "compute/disk",
    "microsoft.compute/snapshots": "compute/snapshot",
    "microsoft.containerservice/managedclusters": "containers/aks",
    "microsoft.containerregistry/registries": "containers/acr",
    "microsoft.storage/storageaccounts": "storage/account",
    "microsoft.network/publicipaddresses": "network/publicip",
    "microsoft.network/networkinterfaces": "network/nic",
    "microsoft.network/natgateways": "network/nat",
    "microsoft.network/loadbalancers": "network/loadbalancer",
    "microsoft.network/applicationgateways": "network/appgateway",
    "microsoft.network/networksecuritygroups": "network/nsg",
    "microsoft.network/virtualnetworks": "network/vnet",
    "microsoft.network/privateendpoints": "network/privateendpoint",
    "microsoft.network/privatelinkservices": "network/privatelinkservice",
    "microsoft.network/privatednszones": "network/privatedns",
    "microsoft.network/azurefirewalls": "network/firewall",
    "microsoft.network/expressroutecircuits": "network/expressroute",
    "microsoft.network/frontdoors": "network/frontdoor",
    "microsoft.network/trafficmanagerprofiles": "network/trafficmanager",
    "microsoft.web/sites": "appservice/webapp",
    "microsoft.web/serverfarms": "appservice/plan",
    "microsoft.sql/servers": "database/sql",
    "microsoft.documentdb/databaseaccounts": "database/cosmosdb",
    "microsoft.dbforpostgresql/flexibleservers": "database/postgresql",
    "microsoft.cache/redis": "database/redis",
    "microsoft.keyvault/vaults": "security/keyvault",
    "microsoft.operationalinsights/workspaces": "monitoring/loganalytics",
    "microsoft.insights/components": "monitoring/appinsights",
    "microsoft.apimanagement/service": "integration/apim",
    "microsoft.datafactory/factories": "integration/datafactory",
    "microsoft.logic/workflows": "integration/logicapp",
    "microsoft.eventhub/namespaces": "messaging/eventhub",
    "microsoft.servicebus/namespaces": "messaging/servicebus",
    "microsoft.databricks/workspaces": "analytics/databricks",
    "microsoft.synapse/workspaces": "analytics/synapse",
    "microsoft.kusto/clusters": "analytics/adx",
    "microsoft.machinelearningservices/workspaces": "analytics/mlworkspace",
    "microsoft.recoveryservices/vaults": "backup/recoveryvault",
    "microsoft.search/searchservices": "search/cognitivesearch",
    "microsoft.cdn/profiles": "network/cdn",
}

_RULE_PREFIX_CANONICAL: tuple[tuple[str, str], ...] = (
    ("STORAGE_", "storage/account"),
    ("DISK_", "compute/disk"),
    ("SNAPSHOT_", "compute/snapshot"),
    ("VMSS_", "compute/vmss"),
    ("VM_", "compute/vm"),
    ("AKS_", "containers/aks"),
    ("ACR_", "containers/acr"),
    ("COSMOS_", "database/cosmosdb"),
    ("POSTGRESQL_", "database/postgresql"),
    ("REDIS_", "database/redis"),
    ("SQL_", "database/sql"),
    ("ASP_", "appservice/plan"),
    ("APP_SERVICE_PLAN", "appservice/plan"),
    ("PLAN_", "appservice/plan"),
    ("WEBAPP_", "appservice/webapp"),
    ("APP_", "appservice/webapp"),
    ("LOAD_BALANCER_", "network/loadbalancer"),
    ("LB_", "network/loadbalancer"),
    ("NAT_GATEWAY_", "network/nat"),
    ("APP_GATEWAY_", "network/appgateway"),
    ("APPGW_", "network/appgateway"),
    ("PUBLIC_IP_", "network/publicip"),
    ("IP_", "network/publicip"),
    ("NSG_", "network/nsg"),
    ("NIC_", "network/nic"),
    ("VNET_", "network/vnet"),
    ("PRIVATE_ENDPOINT_", "network/privateendpoint"),
    ("PRIVATE_LINK_", "network/privatelinkservice"),
    ("PRIVATE_DNS_", "network/privatedns"),
    ("KEYVAULT_", "security/keyvault"),
    ("FIREWALL_", "network/firewall"),
    ("CDN_", "network/cdn"),
    ("NETWORK_EXPRESSROUTE", "network/expressroute"),
    ("NETWORK_FRONT_DOOR", "network/frontdoor"),
    ("NETWORK_TRAFFIC_MANAGER", "network/trafficmanager"),
    ("NETWORK_DDOS", "network/publicip"),
    ("BANDWIDTH_", "network/publicip"),
    ("FUNCTIONS_", "appservice/webapp"),
    ("LOG_ANALYTICS_", "monitoring/loganalytics"),
    ("APP_INSIGHTS_", "monitoring/appinsights"),
    ("API_MANAGEMENT_", "integration/apim"),
    ("DATA_FACTORY_", "integration/datafactory"),
    ("LOGIC_APP_", "integration/logicapp"),
    ("EVENT_HUBS_", "messaging/eventhub"),
    ("SERVICE_BUS_", "messaging/servicebus"),
    ("DATABRICKS_", "analytics/databricks"),
    ("SYNAPSE_", "analytics/synapse"),
    ("ADX_", "analytics/adx"),
    ("ML_WORKSPACE_", "analytics/mlworkspace"),
    ("BACKUP_", "backup/recoveryvault"),
    ("COGNITIVE_SEARCH_", "search/cognitivesearch"),
)


@lru_cache(maxsize=1)
def _load_defaults() -> dict[str, Any]:
    if not _DEFAULTS_PATH.is_file():
        return {}
    with _DEFAULTS_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=32)
def _load_service_spec(canonical_type: str) -> dict[str, Any]:
    rel = CANONICAL_THRESHOLDS_PATHS.get(canonical_type)
    if not rel:
        return {}
    path = _ROOT / rel
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def azure_service_display_name(
    *,
    azure_service_name: str | None = None,
    canonical_type: str | None = None,
    arm_type: str | None = None,
    resource_id: str | None = None,
) -> str | None:
    """Billing service name with fallback from canonical or ARM resource type."""
    billing = (azure_service_name or "").strip()
    if billing:
        return billing

    canonical = (canonical_type or "").strip().lower()
    if not canonical or canonical == "generic":
        canonical = resolve_canonical_type(arm_type or "", "")

    if not canonical or canonical == "generic":
        rid = (resource_id or "").strip().lower()
        for arm_key, canon in _ARM_TO_CANONICAL.items():
            if f"/{arm_key}/" in rid:
                canonical = canon
                break

    from app.optimizer.component_map import CANONICAL_TO_COMPONENT

    label = CANONICAL_TO_COMPONENT.get(canonical)
    if label:
        return label

    arm = (arm_type or "").strip()
    if "/" in arm:
        segment = arm.split("/", 1)[-1]
        return segment.replace("virtualmachines", "Virtual machines").replace("_", " ").title()
    if arm:
        return arm
    return None


def resolve_canonical_type(resource_type: str = "", rule_id: str = "") -> str:
    """Resolve canonical service type from resource type or rule id."""
    rtype = (resource_type or "").strip().lower()
    if rtype in _ARM_TO_CANONICAL.values():
        return rtype
    if rtype in _ARM_TO_CANONICAL:
        return _ARM_TO_CANONICAL[rtype]
    if "/providers/" in rtype:
        parts = rtype.split("/providers/")[-1].split("/")
        if len(parts) >= 2:
            arm = f"{parts[0]}/{parts[1]}".lower()
            if arm in _ARM_TO_CANONICAL:
                return _ARM_TO_CANONICAL[arm]
    rid = (rule_id or "").upper()
    for prefix, canonical in _RULE_PREFIX_CANONICAL:
        if rid.startswith(prefix):
            return canonical
    if "/" in rtype:
        return rtype
    return "generic"


def missing_display(canonical_type: str | None = None) -> str:
    spec = _load_service_spec(canonical_type or "")
    display = spec.get("display") if spec else None
    if isinstance(display, dict) and display.get("missing_value"):
        return str(display["missing_value"])
    defaults = _load_defaults().get("display") or {}
    return str(defaults.get("missing_value") or "Not synced")


def inventory_missing_display() -> str:
    defaults = _load_defaults().get("display") or {}
    return str(defaults.get("inventory_missing") or "Not in inventory sync")


def zero_display(canonical_type: str | None, fact_key: str) -> str | None:
    key = (fact_key or "").strip()
    if not key:
        return None
    spec = _load_service_spec(canonical_type or "")
    display = spec.get("display") if spec else None
    if isinstance(display, dict):
        zero_values = display.get("zero_values") or {}
        if key in zero_values:
            return str(zero_values[key])
        lower = key.lower()
        for zk, label in zero_values.items():
            if zk.lower() == lower:
                return str(label)
        if key == "used_capacity_bytes" and display.get("zero_capacity"):
            return str(display["zero_capacity"])
        if key == "transaction_count" and display.get("zero_transactions"):
            return str(display["zero_transactions"])
    defaults = (_load_defaults().get("display") or {}).get("zero_values") or {}
    if key in defaults:
        return str(defaults[key])
    lower = key.lower()
    for zk, label in defaults.items():
        if zk.lower() == lower:
            return str(label)
    return None


def format_service_fact(
    canonical_type: str | None,
    fact_key: str,
    value: Any,
    *,
    unit: str | None = None,
) -> str:
    """Format a metric for UI — None is missing, 0 is explicit zero when configured."""
    if value is None or value == "":
        return missing_display(canonical_type)

    if canonical_type == "storage/account":
        return format_storage_fact(fact_key, value)

    if isinstance(value, bool):
        return "Yes" if value else "No"

    try:
        if float(value) == 0:
            zero_label = zero_display(canonical_type, fact_key)
            if zero_label:
                return zero_label
    except (TypeError, ValueError):
        pass

    return format_fact_display_value(fact_key, value, unit)


def format_threshold_display(
    canonical_type: str | None,
    fact_key: str,
    threshold_value: Any,
    *,
    comparator: str = "",
    threshold_literal: str | None = None,
) -> str:
    if threshold_literal:
        return threshold_literal
    if threshold_value is None or threshold_value == "":
        return "—"
    prefix_map = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤"}
    prefix = prefix_map.get((comparator or "").lower(), "")
    formatted = format_service_fact(canonical_type, fact_key, threshold_value)
    if prefix and formatted not in ("—", missing_display(canonical_type)):
        return f"{prefix} {formatted}"
    return formatted


def make_service_check(
    canonical_type: str | None,
    signal: str,
    fact_key: str,
    value: Any,
    threshold_display: str,
    *,
    passed: bool,
    status: str | None = None,
) -> dict[str, Any]:
    """Evidence check with human-readable observed/criterion values."""
    from app.resource_utilization import make_check

    if value is None and status is None:
        return make_check(
            signal,
            None,
            threshold_display,
            passed=False,
            status="na",
            value_display=missing_display(canonical_type),
            threshold_display=threshold_display,
            fact_key=fact_key,
        )
    return make_check(
        signal,
        value,
        threshold_display,
        passed=passed,
        status=status,
        value_display=format_service_fact(canonical_type, fact_key, value),
        threshold_display=threshold_display,
        fact_key=fact_key,
    )


def enrich_service_evidence_properties(
    canonical_type: str,
    props: dict[str, Any] | None,
) -> dict[str, Any]:
    """Add display-friendly fields for finding evidence panels."""
    props = dict(props or {})
    if canonical_type == "storage/account":
        return enrich_storage_evidence_properties(props)

    sku = props.get("sku")
    sku_name = sku_text(sku) if sku else props.get("sku_name")
    if sku_name and not props.get("sku_display"):
        props["sku_display"] = format_service_fact(canonical_type, "sku", sku_name)

    tier = props.get("accessTier") or props.get("access_tier") or props.get("tier")
    if tier and not props.get("tier_display"):
        props["tier_display"] = format_service_fact(canonical_type, "tier", tier)

    power = props.get("powerState") or props.get("power_state")
    if power and not props.get("power_state_display"):
        text = power.get("code") if isinstance(power, dict) else str(power)
        props["power_state_display"] = text.replace("PowerState/", "") if text else "—"

    return props


def recommendation_text(canonical_type: str, template_key: str, **kwargs: Any) -> str:
    spec = _load_service_spec(canonical_type)
    templates = spec.get("recommendations") or {}
    template = templates.get(template_key) or ""
    if not template:
        return ""
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError, TypeError):
        return template


# ─── Storage account helpers ───────────────────────────────────────────────────


def format_access_tier(tier: str | None) -> str:
    if tier is None or str(tier).strip() == "":
        return "—"
    spec = access_tier_spec(tier)
    return str(spec.get("display_name") or tier).strip()


def format_replication_sku(sku_name: str | None) -> str:
    if not sku_name or not str(sku_name).strip():
        return "—"
    return replication_display_name(sku_name)


def format_storage_fact(fact_key: str, value: Any) -> str:
    """Format a storage metric — None is missing, 0 is explicit zero."""
    if value is None or value == "":
        return missing_display("storage/account")
    key = (fact_key or "").lower()
    if key in {"used_capacity_bytes", "egress_bytes"}:
        num = float(value)
        if num <= 0:
            zero = zero_display("storage/account", key)
            return zero or ("0 GB used" if key == "used_capacity_bytes" else "0 GB")
        return format_fact_display_value(fact_key, value)
    if key == "transaction_count":
        num = float(value)
        if num <= 0:
            return zero_display("storage/account", key) or "0 transactions"
        return format_fact_display_value(fact_key, value, "count")
    if key == "storage_pct":
        return format_fact_display_value(fact_key, value, "percent")
    if key in {"access_tier", "accesstier"}:
        return format_access_tier(str(value))
    if key in {"sku", "sku_name"}:
        return format_replication_sku(str(value))
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return format_fact_display_value(fact_key, value)


def format_bytes_threshold_gb(bytes_value: float) -> str:
    gb = float(bytes_value) / _GB
    if gb >= 1:
        return f"{gb:,.0f} GB/month"
    return format_fact_display_value("egress_bytes", bytes_value)


def format_transaction_threshold(count: float) -> str:
    return f"< {int(count):,} transactions/month"


def format_storage_utilization_threshold(pct: float) -> str:
    return f"< {pct:.0f}% utilization"


def storage_lifecycle_recommendation(*, cool_days: int | None = None, archive_days: int | None = None) -> str:
    th = storage_optimization_thresholds()
    return storage_recommendation_text(
        "lifecycle",
        cool_days=int(cool_days if cool_days is not None else th.get("lifecycle_cool_after_days", 30)),
        archive_days=int(archive_days if archive_days is not None else th.get("lifecycle_archive_after_days", 90)),
    )


def storage_cool_tier_recommendation(*, cool_days: int, savings_pct: int) -> str:
    return storage_recommendation_text("cool_tier", cool_days=cool_days, savings_pct=savings_pct)


def storage_egress_recommendation() -> str:
    return storage_recommendation_text("egress")


def storage_redundancy_downgrade_recommendation(target_sku: str = "LRS or ZRS") -> str:
    return storage_recommendation_text("redundancy_downgrade", target_sku=target_sku)


def storage_redundancy_upgrade_recommendation() -> str:
    return storage_recommendation_text("redundancy_upgrade")


def storage_hot_tier_recommendation() -> str:
    return storage_recommendation_text("hot_tier_review")


def make_storage_check(
    signal: str,
    fact_key: str,
    value: Any,
    threshold_display: str,
    *,
    passed: bool,
    status: str | None = None,
) -> dict[str, Any]:
    return make_service_check(
        "storage/account",
        signal,
        fact_key,
        value,
        threshold_display,
        passed=passed,
        status=status,
    )


def enrich_storage_evidence_properties(props: dict[str, Any] | None) -> dict[str, Any]:
    props = dict(props or {})
    tier = props.get("accessTier") or props.get("access_tier")
    if tier:
        props["access_tier_display"] = format_access_tier(str(tier))
    sku = props.get("sku")
    sku_name = sku.get("name") if isinstance(sku, dict) else props.get("sku_name")
    if sku_name:
        props["sku_display"] = format_replication_sku(str(sku_name))
    return props
