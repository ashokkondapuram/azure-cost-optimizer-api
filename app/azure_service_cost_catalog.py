"""Azure service and ARM resource cost classification catalog.

Loads the full Azure service list from data/azure_service_catalog.json (built from
the Azure Retail Prices API via scripts/build_azure_service_catalog.py).

Cost types:
  - costed: resource/service directly generates billable meters when deployed
  - free: no Azure charge for this resource type
  - conditional: service category is billable but base resource is often $0
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

CostType = Literal["costed", "free", "conditional"]

_CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "azure_service_catalog.json"


@lru_cache(maxsize=1)
def _load_catalog_document() -> dict[str, Any]:
    if not _CATALOG_PATH.is_file():
        return {"services": [], "aliases": {}, "service_count": 0}
    with _CATALOG_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _service_rows() -> tuple[dict[str, Any], ...]:
    return tuple(_load_catalog_document().get("services") or [])


@lru_cache(maxsize=1)
def _service_by_name() -> dict[str, dict[str, Any]]:
    return {(row.get("service_name") or "").strip(): row for row in _service_rows() if row.get("service_name")}


@lru_cache(maxsize=1)
def _service_aliases() -> dict[str, str]:
    doc = _load_catalog_document()
    aliases = dict(doc.get("aliases") or {})
    for row in _service_rows():
        name = (row.get("service_name") or "").strip()
        if name:
            aliases[name.lower()] = name
    return aliases


# Backward-compatible export: full service table from JSON.
AZURE_SERVICE_COST_TABLE: tuple[dict[str, Any], ...] = _service_rows()


# ARM provider/type (lowercase) → catalog cost type.
_ARM_COST_TYPE: dict[str, CostType] = {
    # Compute
    "microsoft.compute/virtualmachines": "costed",
    "microsoft.compute/virtualmachinescalesets": "costed",
    "microsoft.compute/disks": "costed",
    "microsoft.compute/snapshots": "costed",
    "microsoft.compute/galleries": "conditional",
    "microsoft.compute/images": "conditional",
    "microsoft.compute/availabilitysets": "free",
    "microsoft.compute/proximityplacementgroups": "free",
    "microsoft.compute/capacityreservationgroups": "costed",
    "microsoft.compute/sshpublickeys": "free",
    "microsoft.batch/batchaccounts": "costed",
    "microsoft.desktopvirtualization/hostpools": "costed",
    "microsoft.desktopvirtualization/workspaces": "costed",
    "microsoft.desktopvirtualization/applicationgroups": "costed",
    "microsoft.desktopvirtualization/scalingplans": "costed",
    # Containers
    "microsoft.containerservice/managedclusters": "costed",
    "microsoft.containerregistry/registries": "conditional",
    "microsoft.containerinstance/containergroups": "costed",
    "microsoft.app/containerapps": "costed",
    "microsoft.app/managedenvironments": "costed",
    # Storage
    "microsoft.storage/storageaccounts": "costed",
    "microsoft.storagecache/amlfilesystems": "costed",
    "microsoft.elasticsan/elasticsans": "costed",
    "microsoft.netapp/netappaccounts": "costed",
    "microsoft.databox/jobs": "costed",
    "microsoft.databoxedge/databoxedgedevices": "costed",
    # Network — costed
    "microsoft.network/publicipaddresses": "costed",
    "microsoft.network/publicipprefixes": "costed",
    "microsoft.network/natgateways": "costed",
    "microsoft.network/loadbalancers": "costed",
    "microsoft.network/applicationgateways": "costed",
    "microsoft.network/applicationgatewaywebapplicationfirewallpolicies": "costed",
    "microsoft.network/azurefirewalls": "costed",
    "microsoft.network/firewallpolicies": "costed",
    "microsoft.network/privateendpoints": "costed",
    "microsoft.network/privatelinkservices": "costed",
    "microsoft.network/privatednszones": "costed",
    "microsoft.network/privatednszones/virtualnetworklinks": "free",
    "microsoft.network/vpngateways": "costed",
    "microsoft.network/virtualwans": "costed",
    "microsoft.network/virtualwanvpnsites": "costed",
    "microsoft.network/expressroutecircuits": "costed",
    "microsoft.network/expressrouteports": "costed",
    "microsoft.network/frontdoors": "costed",
    "microsoft.network/frontdoorwebapplicationfirewallpolicies": "costed",
    "microsoft.cdn/profiles": "costed",
    "microsoft.cdn/profiles/endpoints": "costed",
    "microsoft.network/routeservers": "costed",
    "microsoft.network/networkwatchers": "conditional",
    "microsoft.network/networkwatchers/flowlogs": "costed",
    "microsoft.network/virtualnetworkmanagers": "costed",
    "microsoft.network/bastionhosts": "costed",
    "microsoft.network/trafficmanagerprofiles": "costed",
    "microsoft.network/ddosprotectionplans": "costed",
    "microsoft.network/ipgroups": "free",
    "microsoft.network/networkintentpolicies": "free",
    # Network — free / conditional base
    "microsoft.network/virtualnetworks": "conditional",
    "microsoft.network/virtualnetworks/subnets": "free",
    "microsoft.network/networkinterfaces": "free",
    "microsoft.network/networksecuritygroups": "free",
    "microsoft.network/networksecuritygroups/securityrules": "free",
    "microsoft.network/routetables": "free",
    "microsoft.network/routetables/routes": "free",
    "microsoft.network/dnszones": "conditional",
    "microsoft.network/privatednszones/a": "free",
    "microsoft.network/virtualnetworkgateways": "costed",
    "microsoft.network/localnetworkgateways": "free",
    "microsoft.network/connections": "costed",
    # Databases
    "microsoft.sql/servers": "costed",
    "microsoft.sql/servers/databases": "costed",
    "microsoft.sql/servers/elasticpools": "costed",
    "microsoft.sql/managedinstances": "costed",
    "microsoft.documentdb/databaseaccounts": "costed",
    "microsoft.dbforpostgresql/flexibleservers": "costed",
    "microsoft.dbforpostgresql/servers": "costed",
    "microsoft.cache/redis": "costed",
    "microsoft.cache/redisenterprise": "costed",
    "microsoft.dbformysql/flexibleservers": "costed",
    "microsoft.dbformysql/servers": "costed",
    "microsoft.dbformariadb/servers": "costed",
    "microsoft.synapse/workspaces": "costed",
    "microsoft.synapse/workspaces/sqlpools": "costed",
    "microsoft.synapse/workspaces/bigdatapools": "costed",
    "microsoft.kusto/clusters": "costed",
    "microsoft.datamigration/services": "costed",
    # App platform
    "microsoft.web/sites": "costed",
    "microsoft.web/serverfarms": "costed",
    "microsoft.web/staticsites": "conditional",
    "microsoft.web/hostingenvironments": "costed",
    "microsoft.web/certificates": "conditional",
    "microsoft.web/connections": "free",
    # Security & identity
    "microsoft.keyvault/vaults": "conditional",
    "microsoft.keyvault/managedhsms": "costed",
    "microsoft.security/pricings": "conditional",
    "microsoft.security/automations": "conditional",
    "microsoft.aadiam/azureadreports": "conditional",
    "microsoft.aadiam/privatelinkforazuread": "costed",
    "microsoft.managedidentity/userassignedidentities": "free",
    "microsoft.managedidentity/systemassignedidentities": "free",
    # Monitoring
    "microsoft.operationalinsights/workspaces": "costed",
    "microsoft.insights/components": "conditional",
    "microsoft.insights/metricalerts": "conditional",
    "microsoft.insights/activitylogalerts": "conditional",
    "microsoft.insights/datacollectionrules": "conditional",
    "microsoft.insights/datacollectionendpoints": "conditional",
    "microsoft.alertsmanagement/smartdetectoralertrules": "conditional",
    "microsoft.alertsmanagement/prometheusrulegroups": "conditional",
    # Integration
    "microsoft.logic/workflows": "costed",
    "microsoft.logic/integrationaccounts": "costed",
    "microsoft.datafactory/factories": "costed",
    "microsoft.apimanagement/service": "costed",
    "microsoft.eventgrid/topics": "costed",
    "microsoft.eventgrid/domains": "costed",
    "microsoft.eventgrid/systemtopics": "costed",
    # Messaging
    "microsoft.eventhub/namespaces": "costed",
    "microsoft.servicebus/namespaces": "costed",
    "microsoft.signalrservice/webpubsub": "costed",
    "microsoft.signalrservice/signalr": "costed",
    "microsoft.notificationhubs/namespaces": "conditional",
    # Analytics & ML
    "microsoft.databricks/workspaces": "costed",
    "microsoft.hdinsight/clusters": "costed",
    "microsoft.machinelearningservices/workspaces": "costed",
    "microsoft.machinelearningservices/workspaces/computes": "costed",
    "microsoft.powerbidedicated/capacities": "costed",
    "microsoft.purview/accounts": "costed",
    "microsoft.streamanalytics/streamingjobs": "costed",
    # AI / Cognitive
    "microsoft.cognitiveservices/accounts": "costed",
    "microsoft.cognitiveservices/accounts/projects": "costed",
    "microsoft.botservice/botservices": "costed",
    "microsoft.search/searchservices": "costed",
    # IoT
    "microsoft.devices/iothubs": "costed",
    "microsoft.devices/provisioningservices": "costed",
    "microsoft.digitaltwins/digitaltwinsinstances": "costed",
    "microsoft.maps/accounts": "conditional",
    # Backup & automation
    "microsoft.recoveryservices/vaults": "costed",
    "microsoft.recoveryservices/vaults/replicationfabrics": "costed",
    "microsoft.automation/automationaccounts": "conditional",
    "microsoft.automation/automationaccounts/runbooks": "conditional",
    # Management — free
    "microsoft.resources/resourcegroups": "free",
    "microsoft.resources/deployments": "free",
    "microsoft.resources/tags": "free",
    "microsoft.authorization/roleassignments": "free",
    "microsoft.authorization/roledefinitions": "free",
    "microsoft.authorization/policyassignments": "free",
    "microsoft.authorization/policydefinitions": "free",
    "microsoft.policyinsights/remediations": "free",
    "microsoft.portal/dashboards": "free",
    "microsoft.resourcegraph/queries": "free",
    "microsoft.management/managementgroups": "free",
    "microsoft.blueprint/blueprints": "free",
    "microsoft.blueprint/blueprintassignments": "free",
    # Developer tools
    "microsoft.devtestlab/labs": "costed",
    "microsoft.visualstudio/account": "conditional",
    "microsoft.appconfiguration/configurationstores": "conditional",
    # Communication
    "microsoft.communication/communicationservices": "costed",
    "microsoft.communication/emailservices": "costed",
}

# Canonical resource_snapshots.resource_type → cost type.
_CANONICAL_COST_TYPE: dict[str, CostType] = {
    "compute/vm": "costed",
    "compute/vmss": "costed",
    "compute/disk": "costed",
    "compute/snapshot": "costed",
    "compute/batch": "costed",
    "compute/avd": "costed",
    "containers/aks": "costed",
    "containers/acr": "conditional",
    "containers/aci": "costed",
    "storage/account": "costed",
    "network/publicip": "costed",
    "network/vnet": "conditional",
    "network/nic": "free",
    "network/nat": "costed",
    "network/loadbalancer": "costed",
    "network/appgateway": "costed",
    "network/nsg": "free",
    "network/privateendpoint": "costed",
    "network/privatelinkservice": "costed",
    "network/privatedns": "costed",
    "network/dns": "conditional",
    "network/frontdoor": "costed",
    "network/firewall": "costed",
    "network/expressroute": "costed",
    "network/vpngateway": "costed",
    "network/cdn": "costed",
    "database/sql": "costed",
    "database/cosmosdb": "costed",
    "database/postgresql": "costed",
    "database/redis": "costed",
    "database/mysql": "costed",
    "appservice/webapp": "costed",
    "appservice/plan": "costed",
    "appservice/staticweb": "conditional",
    "security/keyvault": "conditional",
    "monitoring/loganalytics": "costed",
    "monitoring/appinsights": "conditional",
    "monitoring/alerts": "conditional",
    "integration/logicapp": "costed",
    "integration/datafactory": "costed",
    "integration/apim": "costed",
    "messaging/eventhub": "costed",
    "messaging/servicebus": "costed",
    "messaging/signalr": "costed",
    "analytics/databricks": "costed",
    "analytics/synapse": "costed",
    "analytics/adx": "costed",
    "analytics/hdinsight": "costed",
    "analytics/mlworkspace": "costed",
    "analytics/powerbi": "costed",
    "backup/recoveryvault": "costed",
    "automation/automation": "conditional",
    "search/cognitivesearch": "costed",
}


@dataclass(frozen=True)
class CostClassification:
    cost_type: CostType
    service_name: str | None = None
    pricing_model: str | None = None
    source: str = "unknown"
    free_tier: dict[str, Any] | None = None

    @property
    def is_cost_bearing(self) -> bool:
        return self.cost_type == "costed"

    @property
    def is_free(self) -> bool:
        return self.cost_type == "free"

    def visible_on_dashboard(self, cost_mtd: float = 0.0, *, inventory: int = 0) -> bool:
        if self.cost_type == "free":
            return False
        if self.cost_type == "costed":
            return inventory > 0
        return cost_mtd > 0 and inventory > 0


def _metadata_for_classification(
    *,
    canonical: str = "",
    arm: str = "",
    service_name: str = "",
    catalog_row: dict[str, Any] | None = None,
) -> tuple[CostType | None, str | None, dict[str, Any] | None]:
    """Resolve cost_type, pricing_model, and free_tier from reference + catalog."""
    from app.free_tier_reference import (
        arm_type_free_tier_entry,
        canonical_free_tier_entry,
        official_free_tier_for_service,
        service_free_tier_entry,
    )

    ref_entry: dict[str, Any] | None = None
    if canonical:
        ref_entry = canonical_free_tier_entry(canonical)
    if not ref_entry and arm:
        ref_entry = arm_type_free_tier_entry(arm)
    if not ref_entry and service_name:
        ref_entry = service_free_tier_entry(service_name)

    cost_type: CostType | None = None
    pricing_model: str | None = None
    free_tier: dict[str, Any] | None = None

    if ref_entry:
        cost_type = ref_entry.get("cost_type")
        pricing_model = ref_entry.get("pricing_model")
        free_tier = ref_entry.get("free_tier")

    if catalog_row:
        if not pricing_model:
            pricing_model = catalog_row.get("pricing_model")
        if not free_tier and catalog_row.get("free_tier"):
            free_tier = dict(catalog_row["free_tier"])
        if not cost_type:
            cost_type = catalog_row.get("cost_type")

    if not free_tier and service_name:
        official = official_free_tier_for_service(service_name)
        if official:
            free_tier = official

    return cost_type, pricing_model, free_tier


def _make_classification(
    *,
    cost_type: CostType,
    source: str,
    service_name: str | None = None,
    pricing_model: str | None = None,
    free_tier: dict[str, Any] | None = None,
    canonical: str = "",
    arm: str = "",
    catalog_row: dict[str, Any] | None = None,
) -> CostClassification:
    ref_cost, ref_model, ref_free = _metadata_for_classification(
        canonical=canonical,
        arm=arm,
        service_name=service_name or "",
        catalog_row=catalog_row,
    )
    return CostClassification(
        cost_type=ref_cost or cost_type,
        service_name=service_name,
        pricing_model=ref_model or pricing_model,
        source=source,
        free_tier=ref_free or free_tier,
    )


def resolve_service_name(service_name: str) -> str | None:
    """Map Cost Management / alias label to canonical catalog service name."""
    key = (service_name or "").strip().lower()
    if not key:
        return None
    aliases = _service_aliases()
    if key in aliases:
        return aliases[key]
    by_name = _service_by_name()
    if service_name in by_name:
        return service_name
    for alias, canonical in aliases.items():
        if alias in key or key in alias:
            return canonical
    for name in by_name:
        low = name.lower()
        if low in key or key in low:
            return name
    return None


def service_catalog_row(service_name: str) -> dict[str, Any] | None:
    canonical = resolve_service_name(service_name) or (service_name or "").strip()
    return _service_by_name().get(canonical)


def cost_type_for_service_name(service_name: str) -> CostType | None:
    row = service_catalog_row(service_name)
    if row:
        return row.get("cost_type")
    return None


def pricing_model_for_service_name(service_name: str) -> str | None:
    row = service_catalog_row(service_name)
    if row:
        return row.get("pricing_model")
    return None


def cost_type_for_arm_type(arm_type: str) -> CostType | None:
    return _ARM_COST_TYPE.get((arm_type or "").strip().lower())


def cost_type_for_canonical(canonical_type: str) -> CostType | None:
    return _CANONICAL_COST_TYPE.get((canonical_type or "").strip().lower())


def classify_resource_type(
    *,
    canonical_type: str = "",
    arm_type: str = "",
    service_name: str = "",
    cost_mtd: float = 0.0,
) -> CostClassification:
    canonical = (canonical_type or "").strip().lower()
    arm = (arm_type or "").strip().lower()
    svc = (service_name or "").strip()
    resolved_svc = resolve_service_name(svc) if svc else None
    catalog_row = service_catalog_row(svc) if svc else None
    pricing_model = catalog_row.get("pricing_model") if catalog_row else None

    if canonical:
        ctype = cost_type_for_canonical(canonical)
        if ctype:
            return _make_classification(
                cost_type=ctype,
                service_name=resolved_svc or svc or None,
                pricing_model=pricing_model,
                source="canonical",
                canonical=canonical,
                arm=arm,
                catalog_row=catalog_row,
            )

    if arm:
        ctype = cost_type_for_arm_type(arm)
        if ctype:
            return _make_classification(
                cost_type=ctype,
                service_name=resolved_svc or svc or None,
                pricing_model=pricing_model,
                source="arm_type",
                canonical=canonical,
                arm=arm,
                catalog_row=catalog_row,
            )

    if svc:
        ctype = cost_type_for_service_name(svc)
        if ctype:
            return _make_classification(
                cost_type=ctype,
                service_name=resolved_svc or svc,
                pricing_model=pricing_model,
                source="service_name",
                canonical=canonical,
                arm=arm,
                catalog_row=catalog_row,
            )

    if cost_mtd > 0:
        return _make_classification(
            cost_type="costed",
            service_name=resolved_svc or svc or None,
            pricing_model=pricing_model,
            source="mtd_cost",
            canonical=canonical,
            arm=arm,
            catalog_row=catalog_row,
        )

    return _make_classification(
        cost_type="free",
        service_name=resolved_svc or svc or None,
        pricing_model=pricing_model,
        source="default_free",
        canonical=canonical,
        arm=arm,
        catalog_row=catalog_row,
    )


def is_cost_bearing_type(
    *,
    canonical_type: str = "",
    arm_type: str = "",
    service_name: str = "",
    cost_mtd: float = 0.0,
    resource_count: int = 0,
) -> bool:
    classification = classify_resource_type(
        canonical_type=canonical_type,
        arm_type=arm_type,
        service_name=service_name,
        cost_mtd=cost_mtd,
    )
    if classification.cost_type == "free":
        return False
    if cost_mtd > 0:
        return True
    if classification.cost_type == "costed" and resource_count > 0:
        return True
    return False


def catalog_metadata() -> dict[str, Any]:
    doc = _load_catalog_document()
    return {
        "version": doc.get("version"),
        "generated_at": doc.get("generated_at"),
        "source": doc.get("source"),
        "service_count": doc.get("service_count") or len(_service_rows()),
    }


def catalog_table_rows() -> list[dict[str, Any]]:
    """Full Azure service cost table for API/docs."""
    return [dict(row) for row in _service_rows()]


def catalog_aliases() -> dict[str, str]:
    return dict(_service_aliases())


def service_free_tier_map() -> dict[str, dict[str, Any]]:
    """Service name → free tier metadata from the full catalog."""
    out: dict[str, dict[str, Any]] = {}
    for row in _service_rows():
        ft = row.get("free_tier")
        if ft:
            out[row["service_name"]] = ft
    return out


def canonical_type_catalog_rows() -> list[dict[str, Any]]:
    from app.free_tier_reference import canonical_free_tier_entry
    from app.resource_pricing import CANONICAL_SKU_PRICING, default_pricing_model_for_canonical
    from app.resource_type_map import arm_types_for_canonical

    rows: list[dict[str, Any]] = []
    for canonical, ctype in sorted(_CANONICAL_COST_TYPE.items()):
        ref = canonical_free_tier_entry(canonical) or {}
        row = {
            "canonical_type": canonical,
            "cost_type": ref.get("cost_type") or ctype,
            "pricing_model": ref.get("pricing_model") or default_pricing_model_for_canonical(canonical),
            "sku_tiers": list(CANONICAL_SKU_PRICING.get(canonical, ())),
            "arm_types": arm_types_for_canonical(canonical),
        }
        if ref.get("free_tier"):
            row["free_tier"] = ref["free_tier"]
        rows.append(row)
    return rows


def arm_type_catalog_rows() -> list[dict[str, Any]]:
    from app.cost_utils import service_label_for_arm_type
    from app.free_tier_reference import arm_type_free_tier_entry
    from app.resource_type_map import ARM_PROVIDER_TO_INTERNAL

    rows: list[dict[str, Any]] = []
    for arm, ctype in sorted(_ARM_COST_TYPE.items()):
        ref = arm_type_free_tier_entry(arm) or {}
        svc = service_label_for_arm_type(arm) or None
        catalog_row = service_catalog_row(svc) if svc else None
        row = {
            "arm_type": arm,
            "cost_type": ref.get("cost_type") or ctype,
            "canonical_type": ARM_PROVIDER_TO_INTERNAL.get(arm),
            "service_name": svc,
            "pricing_model": ref.get("pricing_model") or (catalog_row.get("pricing_model") if catalog_row else None),
        }
        if ref.get("free_tier"):
            row["free_tier"] = ref["free_tier"]
        elif catalog_row and catalog_row.get("free_tier"):
            row["free_tier"] = catalog_row["free_tier"]
        rows.append(row)
    return rows
