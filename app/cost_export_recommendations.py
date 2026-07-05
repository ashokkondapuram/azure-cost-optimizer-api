"""Cost-based recommendations for resources discovered from the blob export (FOCUS CSV).

These rules complement inventory-aware engine checks when resources appear only in
cost data or when service-specific spend patterns warrant review.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable

from app.pricing.savings_calculator import savings_from_retail_or_factor
from app.focus_mapping import normalize_arm_id
from app.inventory_technical import arm_resource_type_for_finding, technical_facts_from_inventory_row
from app.optimizer.component_map import COMPONENT_RESOURCE_TYPES
from app.resource_type_map import extract_rg_from_arm

# Cost-export rules in these components are not scoped to inventory types.
_COST_EXPORT_UNRESTRICTED_COMPONENTS = frozenset({"Cost export"})


@dataclass(frozen=True)
class CostExportRule:
    id: str
    name: str
    category: str
    severity: str
    component: str
    savings_factor: float
    min_monthly_cost: float
    waste_score: int
    confidence: int
    priority: str
    impact: str
    match: Callable[[dict[str, Any]], bool]
    detail: Callable[[dict[str, Any], float], str]
    recommendation: Callable[[dict[str, Any], float], str]


def _monthly_cost(row: dict[str, Any]) -> float:
    billing = row.get("monthlyCostBilling")
    usd = row.get("monthlyCostUsd")
    b = float(billing) if billing is not None else 0.0
    u = float(usd) if usd is not None else 0.0
    return b if b > 0 else u


def _service(row: dict[str, Any]) -> str:
    return (
        row.get("billingServiceName")
        or row.get("azureServiceName")
        or row.get("service_name")
        or ""
    ).strip().lower()


def _canonical_type(row: dict[str, Any]) -> str:
    return (row.get("type") or "").strip().lower()


def _arm_provider(row: dict[str, Any]) -> str:
    props = row.get("properties") or {}
    arm = (props.get("armResourceType") or row.get("sku") or "").strip().lower()
    if arm and "/" in arm:
        return arm
    rid = normalize_arm_id(row.get("id") or "")
    if "/providers/" in rid:
        parts = rid.split("/")
        try:
            idx = parts.index("providers")
            return f"{parts[idx + 1]}/{parts[idx + 2]}".lower()
        except (ValueError, IndexError):
            pass
    return ""


def _match_service(*names: str) -> Callable[[dict[str, Any]], bool]:
    needles = {n.lower() for n in names}

    def _fn(row: dict[str, Any]) -> bool:
        svc = _service(row)
        return any(n in svc for n in needles)

    return _fn


def _match_type_prefix(prefix: str) -> Callable[[dict[str, Any]], bool]:
    def _fn(row: dict[str, Any]) -> bool:
        return _canonical_type(row).startswith(prefix.lower())

    return _fn


def _match_arm(*providers: str) -> Callable[[dict[str, Any]], bool]:
    needles = {p.lower() for p in providers}

    def _fn(row: dict[str, Any]) -> bool:
        return _arm_provider(row) in needles

    return _fn


def _props(row: dict[str, Any]) -> dict[str, Any]:
    props = row.get("properties") or {}
    return props if isinstance(props, dict) else {}


def _component_allows_row(row: dict[str, Any], component: str) -> bool:
    """Cost-export rules only apply to inventory types owned by their component."""
    if component in _COST_EXPORT_UNRESTRICTED_COMPONENTS:
        return True
    ctype = _canonical_type(row)
    if not ctype:
        return False
    if component in ("Networking", "Networking Extended"):
        return ctype.startswith("network/")
    allowed = COMPONENT_RESOURCE_TYPES.get(component, ())
    if not allowed:
        return False
    return ctype in allowed


def _rule_matches_row(row: dict[str, Any], rule: CostExportRule) -> bool:
    if not _component_allows_row(row, rule.component):
        return False
    return bool(rule.match(row))


COST_EXPORT_RULES: list[CostExportRule] = [
    CostExportRule(
        id="COST_HIGH_SPEND_REVIEW",
        name="High monthly spend review",
        category="COST",
        severity="HIGH",
        component="Cost export",
        savings_factor=0.15,
        min_monthly_cost=500.0,
        waste_score=72,
        confidence=70,
        priority="P1",
        impact="Prioritize top spend drivers for rightsizing or decommission",
        match=lambda row: True,
        detail=lambda row, cost: (
            f"'{row.get('name')}' ({_service(row) or _canonical_type(row)}) has "
            f"MTD spend of ${cost:,.2f} in the cost export."
        ),
        recommendation=lambda row, cost: (
            "Review usage, validate ownership, and confirm this resource is still required. "
            "Consider rightsizing, reserved capacity, or decommissioning if utilization is low."
        ),
    ),
    CostExportRule(
        id="COST_EXPORT_ONLY_RESOURCE",
        name="Cost export only — not in Azure inventory",
        category="GOVERNANCE",
        severity="MEDIUM",
        component="Cost export",
        savings_factor=0.20,
        min_monthly_cost=25.0,
        waste_score=58,
        confidence=75,
        priority="P2",
        impact="Surfaces orphaned or untracked spend",
        match=lambda row: bool(row.get("costExportOnly")),
        detail=lambda row, cost: (
            f"'{row.get('name')}' appears in the cost export (${cost:,.2f} MTD) "
            "but is not in synced Azure inventory."
        ),
        recommendation=lambda row, cost: (
            "Sync Azure inventory or validate whether this resource was deleted, moved, "
            "or belongs to another subscription. Remove stale charges if the resource no longer exists."
        ),
    ),
    CostExportRule(
        id="LOG_ANALYTICS_INGESTION",
        name="Log Analytics ingestion review",
        category="COST",
        severity="HIGH",
        component="Monitoring",
        savings_factor=0.30,
        min_monthly_cost=50.0,
        waste_score=65,
        confidence=72,
        priority="P1",
        impact="Reduce observability ingestion cost",
        match=_match_service("log analytics", "microsoft.insights"),
        detail=lambda row, cost: (
            f"Log Analytics workspace '{row.get('name')}' has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Review data collection rules, drop verbose tables, shorten retention, "
            "and use Basic logs or commitment tiers where appropriate."
        ),
    ),
    CostExportRule(
        id="APP_INSIGHTS_SAMPLING",
        name="Application Insights sampling",
        category="COST",
        severity="MEDIUM",
        component="Monitoring",
        savings_factor=0.25,
        min_monthly_cost=30.0,
        waste_score=55,
        confidence=70,
        priority="P2",
        impact="Lower telemetry ingestion without losing signal",
        match=_match_service("application insights", "app insights"),
        detail=lambda row, cost: (
            f"Application Insights component '{row.get('name')}' has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Enable adaptive sampling, cap daily ingestion, and move long-term analytics "
            "to Log Analytics with tuned retention."
        ),
    ),
    CostExportRule(
        id="API_MANAGEMENT_SKU",
        name="API Management SKU review",
        category="COST",
        severity="MEDIUM",
        component="Integration",
        savings_factor=0.35,
        min_monthly_cost=100.0,
        waste_score=60,
        confidence=68,
        priority="P2",
        impact="Right-size API gateway capacity",
        match=lambda row: (
            _match_arm("microsoft.apimanagement/service")(row)
            or _match_service("api management")(row)
        ),
        detail=lambda row, cost: (
            f"API Management instance '{row.get('name')}' has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Validate tier (Developer/Standard/Premium), scale units, and self-hosted gateway needs. "
            "Downgrade non-production gateways where possible."
        ),
    ),
    CostExportRule(
        id="DATA_FACTORY_PIPELINE",
        name="Azure Data Factory spend review",
        category="COST",
        severity="MEDIUM",
        component="Integration",
        savings_factor=0.20,
        min_monthly_cost=75.0,
        waste_score=52,
        confidence=65,
        priority="P2",
        impact="Optimize pipeline and IR runtime cost",
        match=lambda row: (
            _match_arm("microsoft.datafactory/factories")(row)
            or _match_service("data factory")(row)
        ),
        detail=lambda row, cost: (
            f"Data Factory '{row.get('name')}' has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Pause unused pipelines, right-size integration runtimes, use Azure-hosted IR "
            "only when needed, and archive old pipeline history."
        ),
    ),
    CostExportRule(
        id="LOGIC_APP_RUN_HISTORY",
        name="Logic App run history retention",
        category="COST",
        severity="LOW",
        component="Integration",
        savings_factor=0.15,
        min_monthly_cost=40.0,
        waste_score=45,
        confidence=62,
        priority="P3",
        impact="Reduce workflow storage and execution charges",
        match=lambda row: (
            _match_arm("microsoft.logic/workflows")(row)
            or _match_service("logic apps", "logic app")(row)
        ),
        detail=lambda row, cost: (
            f"Logic App '{row.get('name')}' has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Trim run history retention, consolidate workflows, and use Consumption plan "
            "for intermittent workloads instead of dedicated hosts."
        ),
    ),
    CostExportRule(
        id="EVENT_HUBS_TIER",
        name="Event Hubs throughput review",
        category="COST",
        severity="MEDIUM",
        component="Messaging",
        savings_factor=0.25,
        min_monthly_cost=60.0,
        waste_score=50,
        confidence=66,
        priority="P2",
        impact="Align messaging capacity with actual throughput",
        match=lambda row: (
            _match_arm("microsoft.eventhub/namespaces")(row)
            or _match_service("event hubs", "event hub")(row)
        ),
        detail=lambda row, cost: (
            f"Event Hubs namespace '{row.get('name')}' has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Review TU/partition count, enable auto-inflate only if needed, and move dev/test "
            "traffic to Basic or Kafka-enabled Standard tiers."
        ),
    ),
    CostExportRule(
        id="SERVICE_BUS_TIER",
        name="Service Bus tier review",
        category="COST",
        severity="MEDIUM",
        component="Messaging",
        savings_factor=0.25,
        min_monthly_cost=50.0,
        waste_score=48,
        confidence=64,
        priority="P2",
        impact="Reduce messaging fixed capacity cost",
        match=lambda row: (
            _match_arm("microsoft.servicebus/namespaces")(row)
            or _match_service("service bus")(row)
        ),
        detail=lambda row, cost: (
            f"Service Bus namespace '{row.get('name')}' has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Use Standard for most workloads, reduce premium namespaces in non-prod, "
            "and delete idle queues or topics."
        ),
    ),
    CostExportRule(
        id="DATABRICKS_CLUSTER",
        name="Azure Databricks cluster review",
        category="COST",
        severity="HIGH",
        component="Analytics",
        savings_factor=0.30,
        min_monthly_cost=150.0,
        waste_score=68,
        confidence=70,
        priority="P1",
        impact="Cut analytics compute waste",
        match=lambda row: (
            _match_arm("microsoft.databricks/workspaces")(row)
            or _match_service("azure databricks", "databricks")(row)
        ),
        detail=lambda row, cost: (
            f"Databricks workspace '{row.get('name')}' has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Enable auto-termination on clusters, use job clusters instead of all-purpose, "
            "and apply spot instances for non-critical workloads."
        ),
    ),
    CostExportRule(
        id="SYNAPSE_PAUSE",
        name="Azure Synapse pause and scale",
        category="COST",
        severity="HIGH",
        component="Analytics",
        savings_factor=0.35,
        min_monthly_cost=200.0,
        waste_score=70,
        confidence=72,
        priority="P1",
        impact="Reduce warehouse idle compute cost",
        match=lambda row: (
            _match_arm("microsoft.synapse/workspaces")(row)
            or _match_service("azure synapse", "synapse analytics")(row)
        ),
        detail=lambda row, cost: (
            f"Synapse workspace '{row.get('name')}' has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Pause dedicated SQL pools outside business hours, scale DWUs to workload peaks, "
            "and use serverless SQL for ad hoc queries."
        ),
    ),
    CostExportRule(
        id="ADX_INGESTION",
        name="Azure Data Explorer ingestion",
        category="COST",
        severity="MEDIUM",
        component="Analytics",
        savings_factor=0.20,
        min_monthly_cost=100.0,
        waste_score=55,
        confidence=65,
        priority="P2",
        impact="Optimize ADX cluster and retention cost",
        match=lambda row: (
            _match_arm("microsoft.kusto/clusters")(row)
            or _match_service("azure data explorer", "data explorer")(row)
        ),
        detail=lambda row, cost: (
            f"ADX cluster '{row.get('name')}' has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Review ingestion batching, retention policies, cache policy, and scale down "
            "dev/test clusters when idle."
        ),
    ),
    CostExportRule(
        id="ML_WORKSPACE_COMPUTE",
        name="Azure ML workspace compute review",
        category="COST",
        severity="MEDIUM",
        component="Analytics",
        savings_factor=0.25,
        min_monthly_cost=100.0,
        waste_score=54,
        confidence=63,
        priority="P2",
        impact="Reduce ML training and endpoint cost",
        match=lambda row: (
            _match_arm("microsoft.machinelearningservices/workspaces")(row)
            or _match_service("azure machine learning", "machine learning")(row)
        ),
        detail=lambda row, cost: (
            f"ML workspace '{row.get('name')}' has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Delete idle compute clusters, use low-priority VMs for training, "
            "and scale managed online endpoints to zero when unused."
        ),
    ),
    CostExportRule(
        id="BACKUP_RETENTION",
        name="Backup vault retention review",
        category="COST",
        severity="MEDIUM",
        component="Backup",
        savings_factor=0.20,
        min_monthly_cost=75.0,
        waste_score=50,
        confidence=67,
        priority="P2",
        impact="Lower backup storage growth",
        match=lambda row: (
            _match_arm("microsoft.recoveryservices/vaults")(row)
            or _match_service("backup", "recovery services")(row)
        ),
        detail=lambda row, cost: (
            f"Recovery Services vault '{row.get('name')}' has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Shorten retention for non-critical workloads, remove orphaned backup items, "
            "and use archive tier for long-term copies."
        ),
    ),
    CostExportRule(
        id="CDN_EGRESS",
        name="CDN / Front Door egress review",
        category="COST",
        severity="MEDIUM",
        component="Networking",
        savings_factor=0.15,
        min_monthly_cost=80.0,
        waste_score=48,
        confidence=60,
        priority="P2",
        impact="Reduce content delivery and egress charges",
        match=lambda row: (
            _match_arm("microsoft.cdn/profiles", "microsoft.network/frontdoors")(row)
            or _match_service("cdn", "front door")(row)
        ),
        detail=lambda row, cost: (
            f"CDN or Front Door profile '{row.get('name')}' has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Review origin egress, caching rules, rule sets, and consolidate profiles "
            "across environments where possible."
        ),
    ),
    CostExportRule(
        id="FIREWALL_FIXED_COST",
        name="Azure Firewall fixed cost review",
        category="COST",
        severity="MEDIUM",
        component="Networking",
        savings_factor=0.10,
        min_monthly_cost=200.0,
        waste_score=52,
        confidence=58,
        priority="P2",
        impact="Validate dedicated firewall necessity",
        match=_match_arm("microsoft.network/azurefirewalls", "microsoft.network/firewallpolicies"),
        detail=lambda row, cost: (
            f"Firewall resource '{row.get('name')}' has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Confirm hub topology requirements; use NVAs or secured virtual hubs only where "
            "policy mandates a dedicated firewall SKU."
        ),
    ),
    CostExportRule(
        id="COGNITIVE_SEARCH_SKU",
        name="AI Search SKU review",
        category="COST",
        severity="MEDIUM",
        component="Search",
        savings_factor=0.25,
        min_monthly_cost=80.0,
        waste_score=50,
        confidence=64,
        priority="P2",
        impact="Right-size search replicas and partitions",
        match=lambda row: (
            _match_arm("microsoft.search/searchservices")(row)
            or _match_service("search", "cognitive search", "azure search")(row)
        ),
        detail=lambda row, cost: (
            f"Search service '{row.get('name')}' has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Reduce replicas/partitions in non-prod, use basic tier for dev, "
            "and delete unused indexes."
        ),
    ),
    CostExportRule(
        id="BANDWIDTH_REVIEW",
        name="Bandwidth and peering review",
        category="COST",
        severity="LOW",
        component="Networking",
        savings_factor=0.10,
        min_monthly_cost=100.0,
        waste_score=42,
        confidence=55,
        priority="P3",
        impact="Identify cross-region or internet egress drivers",
        match=lambda row: (
            _match_service("bandwidth", "virtual network", "peering", "nat gateway")(row)
            and _canonical_type(row).startswith("network/")
        ),
        detail=lambda row, cost: (
            f"Network-related charge '{row.get('name')}' ({_service(row)}) has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Use Cost Management views to find top egress resources, prefer private endpoints, "
            "and consolidate cross-region traffic."
        ),
    ),
    CostExportRule(
        id="PRIVATE_ENDPOINT_COST",
        name="Private endpoint spend review",
        category="COST",
        severity="MEDIUM",
        component="Networking",
        savings_factor=0.15,
        min_monthly_cost=25.0,
        waste_score=52,
        confidence=62,
        priority="P2",
        impact="Validate private endpoint necessity and connection count",
        match=_match_arm("microsoft.network/privateendpoints"),
        detail=lambda row, cost: (
            f"Private endpoint '{row.get('name')}' has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Remove unused endpoints, consolidate targets, and prefer shared endpoints "
            "where security policy allows."
        ),
    ),
    CostExportRule(
        id="PRIVATE_LINK_COST",
        name="Private link service spend review",
        category="COST",
        severity="MEDIUM",
        component="Networking",
        savings_factor=0.15,
        min_monthly_cost=25.0,
        waste_score=50,
        confidence=60,
        priority="P2",
        impact="Review private link service connections and visibility",
        match=_match_arm("microsoft.network/privatelinkservices", "microsoft.network/privatednszones"),
        detail=lambda row, cost: (
            f"Private link resource '{row.get('name')}' has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Delete unused private link services or empty private DNS zones and "
            "consolidate DNS zone groups on active endpoints."
        ),
    ),
    CostExportRule(
        id="IDLE_APP_SERVICE_PLANS",
        name="Idle App Service plan",
        category="COST",
        severity="HIGH",
        component="App Service",
        savings_factor=0.95,
        min_monthly_cost=5.0,
        waste_score=78,
        confidence=88,
        priority="P1",
        impact="Eliminate App Service plan charges with no hosted apps",
        match=lambda row: (
            _canonical_type(row) == "appservice/plan"
            and int(_props(row).get("numberOfSites") or 0) == 0
        ),
        detail=lambda row, cost: (
            f"App Service plan '{row.get('name')}' hosts no web apps but has "
            f"MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Delete the unused plan or consolidate apps onto a shared plan to stop fixed SKU charges."
        ),
    ),
    CostExportRule(
        id="UNUSED_NIC",
        name="Unattached network interface",
        category="NETWORK",
        severity="MEDIUM",
        component="Network Interfaces",
        savings_factor=0.90,
        min_monthly_cost=1.0,
        waste_score=62,
        confidence=85,
        priority="P2",
        impact="Remove orphaned NICs and any associated public IP charges",
        match=lambda row: (
            _canonical_type(row) == "network/nic"
            and not _props(row).get("virtualMachine")
            and not _props(row).get("privateEndpoint")
        ),
        detail=lambda row, cost: (
            f"NIC '{row.get('name')}' is not attached to a VM or private endpoint "
            f"(MTD spend ${cost:,.2f})."
        ),
        recommendation=lambda row, cost: (
            "Delete the NIC after confirming no load balancer backend or firewall dependency remains."
        ),
    ),
    CostExportRule(
        id="IDLE_NAT_GATEWAY",
        name="Idle NAT gateway",
        category="NETWORK",
        severity="HIGH",
        component="NAT Gateways",
        savings_factor=0.95,
        min_monthly_cost=10.0,
        waste_score=80,
        confidence=90,
        priority="P1",
        impact="Reclaim fixed hourly NAT gateway charges",
        match=lambda row: (
            _canonical_type(row) == "network/nat"
            and not (_props(row).get("subnets") or [])
        ),
        detail=lambda row, cost: (
            f"NAT gateway '{row.get('name')}' has no subnet associations "
            f"but still has MTD spend of ${cost:,.2f}."
        ),
        recommendation=lambda row, cost: (
            "Delete the NAT gateway or attach subnets that require outbound SNAT."
        ),
    ),
    CostExportRule(
        id="IDLE_DB_FLEXIBLE_SERVER",
        name="Stopped flexible database server",
        category="COST",
        severity="MEDIUM",
        component="PostgreSQL",
        savings_factor=0.70,
        min_monthly_cost=1.0,
        waste_score=58,
        confidence=82,
        priority="P2",
        impact="Reduce storage and backup charges on stopped database servers",
        match=lambda row: (
            _arm_provider(row) in (
                "microsoft.dbforpostgresql/flexibleservers",
                "microsoft.dbformysql/flexibleservers",
            )
            and str(_props(row).get("state") or "").lower() == "stopped"
        ),
        detail=lambda row, cost: (
            f"Flexible database server '{row.get('name')}' is stopped but still has "
            f"MTD spend of ${cost:,.2f} (storage/backup)."
        ),
        recommendation=lambda row, cost: (
            "Export data and delete the server if no longer needed, or start it only during required windows."
        ),
    ),
    CostExportRule(
        id="UNCLASSIFIED_SERVICE_SPEND",
        name="Unclassified service spend",
        category="COST",
        severity="LOW",
        component="Cost export",
        savings_factor=0.10,
        min_monthly_cost=50.0,
        waste_score=40,
        confidence=50,
        priority="P3",
        impact="Surface spend on services without dedicated rules",
        match=lambda row: (
            _canonical_type(row).startswith("other/")
            and _monthly_cost(row) >= 50.0
        ),
        detail=lambda row, cost: (
            f"Resource '{row.get('name')}' ({_canonical_type(row)}) has MTD spend of ${cost:,.2f} "
            f"for service '{_service(row) or 'Unknown'}'."
        ),
        recommendation=lambda row, cost: (
            "Classify this workload, assign an owner, and add it to your optimization review queue. "
            "Consider reserved capacity or decommissioning if unused."
        ),
    ),
]


def _row_to_finding(
    subscription_id: str,
    row: dict[str, Any],
    rule: CostExportRule,
    monthly_cost: float,
) -> dict[str, Any]:
    savings, _pricing = savings_from_retail_or_factor(
        None,
        baseline=monthly_cost,
        factor=rule.savings_factor,
        allow_factor_fallback=True,
    )
    rid = normalize_arm_id(row.get("id") or "")
    rg = row.get("resourceGroup") or extract_rg_from_arm(rid)
    tech = technical_facts_from_inventory_row(row)
    arm_type = arm_resource_type_for_finding(
        rid,
        tech.get("arm_resource_type") or _arm_provider(row),
    )
    service = (
        row.get("billingServiceName")
        or row.get("azureServiceName")
        or row.get("service_name")
        or ""
    ).strip()
    location = (tech.get("location") or row.get("location") or "").strip()
    state = (tech.get("state") or row.get("state") or "").strip()
    now = datetime.now(timezone.utc).isoformat()

    evidence: dict[str, Any] = {
        "monthly_cost": round(monthly_cost, 2),
        "monthly_cost_usd": round(monthly_cost, 2),
        "min_monthly_cost": rule.min_monthly_cost,
        "savings_factor": rule.savings_factor,
        "cost_export_only": bool(row.get("costExportOnly")),
        "in_inventory": bool(row.get("inInventory", True)),
        "source": "cost_export",
        "data_source": "cost_export",
        "summary": rule.detail(row, monthly_cost),
        "arm_resource_type": arm_type,
        "azure_service_name": service,
        "resource_group": rg or tech.get("resource_group") or "",
    }
    for key, val in tech.items():
        if key in ("data_source", "arm_resource_type"):
            continue
        if val not in (None, ""):
            evidence.setdefault(key, val)
    props = row.get("properties") or {}
    if props and props.get("source") != "cost_export":
        evidence["properties"] = props

    return {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "category": rule.category,
        "severity": rule.severity,
        "resource_id": rid,
        "resource_name": row.get("name") or "",
        "resource_type": arm_type,
        "subscription_id": subscription_id.lower(),
        "resource_group": rg or tech.get("resource_group") or "",
        "location": location,
        "detail": rule.detail(row, monthly_cost),
        "recommendation": rule.recommendation(row, monthly_cost),
        "estimated_savings_usd": savings,
        "annualized_savings_usd": round(savings * 12, 2),
        "waste_score": rule.waste_score,
        "confidence_score": rule.confidence,
        "action_priority": rule.priority,
        "impact": rule.impact,
        "evidence": evidence,
        "tags": row.get("tags") or {},
        "detected_at": now,
        "state": state,
    }


COST_EXPORT_RULES_BY_ID: dict[str, CostExportRule] = {r.id: r for r in COST_EXPORT_RULES}


def effective_cost_export_rules(
    rule_overrides: dict[str, dict] | None = None,
) -> list[CostExportRule]:
    """Apply profile / request overrides (enabled, min_monthly_cost, savings_factor)."""
    active: list[CostExportRule] = []
    for rule in COST_EXPORT_RULES:
        ov = (rule_overrides or {}).get(rule.id, {})
        if ov.get("enabled") is False:
            continue
        kw: dict[str, float | str] = {}
        for key in ("min_monthly_cost", "savings_factor", "severity"):
            if key in ov:
                kw[key] = float(ov[key]) if key != "severity" else str(ov[key]).upper()
        active.append(replace(rule, **kw) if kw else rule)
    return active


def analyze_cost_export_resources(
    subscription_id: str,
    resources: list[dict[str, Any]],
    *,
    rule_overrides: dict[str, dict] | None = None,
    applied_rule_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Generate findings from cost-export resource rows (one best rule per resource)."""
    subscription_id = subscription_id.lower()
    findings: list[dict[str, Any]] = []
    seen_resource_rules: set[tuple[str, str]] = set()
    active_rules = effective_cost_export_rules(rule_overrides)

    for row in resources:
        monthly = _monthly_cost(row)
        if monthly <= 0:
            continue
        rid = normalize_arm_id(row.get("id") or "")
        if not rid:
            continue

        for rule in active_rules:
            if applied_rule_ids and rule.id not in applied_rule_ids:
                continue
            if monthly < rule.min_monthly_cost:
                continue
            if not _rule_matches_row(row, rule):
                continue
            key = (rid, rule.id)
            if key in seen_resource_rules:
                continue
            seen_resource_rules.add(key)
            findings.append(_row_to_finding(subscription_id, row, rule, monthly))
            break

    findings.sort(
        key=lambda f: (-(f.get("estimated_savings_usd") or 0), f.get("severity", "")),
    )
    return findings
