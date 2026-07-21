"""Declarative evidence contract for every optimization rule.

Each rule documents:
  - determination: why the finding was raised
  - signals: measurable checks (observed value vs threshold)
  - savings: how estimated monthly savings is calculated
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from app.optimizer.rule_catalog import RULE_MANIFEST
from app.optimization_metrics import (
    PERFORMANCE_FACT_KEYS,
    attach_optimization_metrics,
)


@dataclass(frozen=True)
class SignalDef:
    """One measurable criterion for a rule."""
    signal: str
    value_key: str
    threshold_key: str | None = None
    threshold_literal: str | None = None
    # How to decide pass: lte | gte | eq | neq | truthy | falsy | not_empty | empty | below_threshold | above_threshold
    comparator: str = "truthy"
    format_value: Callable[[Any], str] | None = None
    # When True, missing values are informational (N/A) — not a failed check.
    optional: bool = False


@dataclass(frozen=True)
class SavingsDef:
    """How estimated_savings_usd is derived for this rule."""
    method: str
    # full_monthly_cost | factor_of_monthly_cost | azure_retail_sku_diff | per_unit | governance | budget_guardrail
    factor: float | None = None
    factor_key: str | None = "savings_factor"
    description: str = ""


@dataclass(frozen=True)
class RuleEvidenceSpec:
    determination: str
    signals: tuple[SignalDef, ...] = ()
    summary_template: str = ""
    savings: SavingsDef = field(default_factory=lambda: SavingsDef(method="governance", description="No direct savings estimate."))
    data_source: str = "synced_inventory"


def _fmt_pct(v: Any) -> str:
    if v is None:
        return "—"
    return f"{float(v):.1f}%"


def _fmt_money(v: Any) -> str:
    if v is None:
        return "—"
    return f"${float(v):,.2f}"


def _fmt_storage_tier(v: Any) -> str:
    from app.service_display import format_access_tier
    return format_access_tier(v if v is not None else None)


def _fmt_storage_sku(v: Any) -> str:
    from app.service_display import format_replication_sku
    return format_replication_sku(v if v is not None else None)


def _fmt_storage_bytes(v: Any) -> str:
    from app.service_display import format_storage_fact
    return format_storage_fact("egress_bytes", v)


def _fmt_storage_transactions(v: Any) -> str:
    from app.service_display import format_storage_fact
    return format_storage_fact("transaction_count", v)


def _spec(
    determination: str,
    *,
    signals: tuple[SignalDef, ...] = (),
    summary: str = "",
    savings_method: str = "governance",
    savings_factor: float | None = None,
    savings_factor_key: str | None = "savings_factor",
    savings_desc: str = "",
    data_source: str = "synced_inventory",
) -> RuleEvidenceSpec:
    desc = savings_desc or {
        "full_monthly_cost": "Estimated savings equals month-to-date billed cost if the resource is removed.",
        "factor_of_monthly_cost": "Estimated savings = month-to-date cost × savings factor (conservative scenario).",
        "azure_retail_sku_diff": (
            "Estimated savings = monthly run-rate × (1 − suggested retail ÷ current retail) "
            "when billed cost is available; otherwise Azure retail list-price delta."
        ),
        "per_unit": "Estimated savings based on unit count × per-unit monthly cost.",
        "governance": "Governance or reliability finding — no direct cost savings estimated.",
        "budget_guardrail": "Budget guardrail — savings depend on remediation actions taken.",
    }.get(savings_method, "")
    return RuleEvidenceSpec(
        determination=determination,
        signals=signals,
        summary_template=summary,
        savings=SavingsDef(
            method=savings_method,
            factor=savings_factor,
            factor_key=savings_factor_key,
            description=desc,
        ),
        data_source=data_source,
    )


_APP_GATEWAY_LOW_THROUGHPUT_SPEC = _spec(
    "low_throughput",
    signals=(
        SignalDef("HTTP listeners configured", "http_listener_count", threshold_literal="≥ 1", comparator="gte"),
        SignalDef(
            "Throughput",
            "throughput_bytes",
            threshold_literal="low",
            comparator="lte",
            optional=True,
        ),
        SignalDef(
            "Total requests",
            "request_count",
            threshold_literal="low",
            comparator="lte",
            optional=True,
        ),
    ),
    summary="Application Gateway has HTTP listeners but very low throughput in Azure Monitor.",
    savings_method="factor_of_monthly_cost",
    savings_factor=0.4,
    data_source="azure_monitor",
)

_PUBLIC_IP_LOW_TRAFFIC_SPEC = _spec(
    "associated_low_traffic",
    signals=(
        SignalDef("Byte count", "byte_count", threshold_literal="low", comparator="lte", optional=True),
        SignalDef("Packet count", "packet_count", threshold_literal="low", comparator="lte", optional=True),
    ),
    summary="Associated public IP shows negligible traffic in Azure Monitor.",
    savings_method="full_monthly_cost",
    data_source="azure_monitor",
)

_NAT_GATEWAY_LOW_TRAFFIC_SPEC = _spec(
    "associated_low_traffic",
    signals=(
        SignalDef("Byte count", "byte_count", threshold_literal="low", comparator="lte", optional=True),
        SignalDef("SNAT connections", "snat_connection_count", threshold_literal="low", comparator="lte", optional=True),
    ),
    summary="NAT Gateway has subnet associations but negligible traffic in Azure Monitor.",
    savings_method="full_monthly_cost",
    data_source="azure_monitor",
)

_KEYVAULT_IDLE_SPEC = _spec(
    "idle_vault",
    signals=(SignalDef("API hits", "api_hits", threshold_key="kv_api_hits_idle", comparator="lt"),),
    summary="Key Vault shows very low API activity in Azure Monitor.",
    savings_method="full_monthly_cost",
    data_source="azure_monitor",
)

_KEYVAULT_PREMIUM_SPEC = _spec(
    "premium_idle",
    signals=(
        SignalDef("SKU", "sku", threshold_literal="Premium", comparator="contains"),
        SignalDef("API hits", "api_hits", threshold_key="kv_api_hits_idle", comparator="lt"),
    ),
    summary="Premium Key Vault with low API activity in non-production.",
    savings_method="factor_of_monthly_cost",
    savings_factor=0.30,
)

_KEYVAULT_HIGH_OPS_SPEC = _spec(
    "high_api_volume",
    signals=(SignalDef("API hits", "api_hits", threshold_key="kv_api_hits_high", comparator="gte"),),
    summary="Key Vault API hits exceed the high-ops threshold.",
    savings_method="factor_of_monthly_cost",
    savings_factor=0.25,
    data_source="azure_monitor",
)


def resolve_rule_evidence_spec(rule_id: str, facts: dict[str, Any] | None) -> RuleEvidenceSpec | None:
    """Pick the evidence contract variant when a rule has multiple determinations."""
    rid = (rule_id or "").upper()
    determination = str((facts or {}).get("determination") or "").strip().lower()
    if rid == "APP_GATEWAY_IDLE_EXTENDED" and determination == "low_throughput":
        return _APP_GATEWAY_LOW_THROUGHPUT_SPEC
    if rid == "PUBLIC_IP_IDLE_EXTENDED" and determination == "associated_low_traffic":
        return _PUBLIC_IP_LOW_TRAFFIC_SPEC
    if rid == "NAT_GATEWAY_IDLE_EXTENDED" and determination == "associated_low_traffic":
        return _NAT_GATEWAY_LOW_TRAFFIC_SPEC
    if rid == "KEYVAULT_IDLE_EXTENDED" and determination == "idle_vault":
        return _KEYVAULT_IDLE_SPEC
    if rid == "KEYVAULT_PREMIUM_EXTENDED":
        return _KEYVAULT_PREMIUM_SPEC
    if rid == "KEYVAULT_HIGH_OPS_EXTENDED" and determination == "high_api_volume":
        return _KEYVAULT_HIGH_OPS_SPEC
    return RULE_EVIDENCE_SPECS.get(rid)


def _cpu_signal(threshold_key: str = "cpu_threshold_pct", default: float = 5.0) -> SignalDef:
    return SignalDef(
        "Average CPU utilization",
        "avg_cpu_pct",
        threshold_key=threshold_key,
        threshold_literal=f"≤ {default}%",
        comparator="lte",
        format_value=_fmt_pct,
    )


RULE_EVIDENCE_SPECS: dict[str, RuleEvidenceSpec] = {
    # ── Compute / VM ───────────────────────────────────────────────────────
    "VM_IDLE": _spec(
        "underutilized_cpu",
        signals=(_cpu_signal("cpu_threshold_pct", 5),),
        summary="Average CPU is {avg_cpu_pct:.1f}% over the evaluation window (idle threshold ≤ {cpu_threshold_pct}%).",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.90,
        savings_desc="Assumes deallocation or removal saves ~90% of current monthly compute cost.",
    ),
    "VM_OVERSIZE": _spec(
        "oversized_sku",
        signals=(
            SignalDef("Average CPU utilization", "avg_cpu_pct", threshold_key="cpu_oversize_threshold_pct",
                      threshold_literal="≤ 20%", comparator="lte", format_value=_fmt_pct),
            SignalDef("Average memory utilization", "avg_memory_pct", threshold_key="mem_idle_pct",
                      threshold_literal="≤ 30%", comparator="lte", format_value=_fmt_pct, optional=True),
            SignalDef("Suggested SKU", "suggested_sku", comparator="not_empty"),
        ),
        summary="VM runs at {avg_cpu_pct:.1f}% CPU on SKU {vm_size}; consider {suggested_sku}.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.35,
    ),
    "VM_NO_RESERVED": _spec(
        "on_demand_running",
        signals=(
            SignalDef("Power state", "power_state", threshold_literal="running", comparator="eq"),
            SignalDef("Pricing model", "pricing_model", threshold_literal="Reserved Instance", comparator="neq"),
        ),
        summary="VM {vm_size} is running on pay-as-you-go pricing without a reservation.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.40,
        savings_desc="Assumes 1-year reserved instance saves ~40% vs on-demand.",
    ),
    "VM_STOPPED_DEALLOCATED": _spec(
        "stopped_not_deallocated",
        signals=(SignalDef("Power state", "power_state", threshold_literal="deallocated", comparator="neq"),),
        summary="VM is stopped but not deallocated — compute charges may still apply.",
        savings_method="full_monthly_cost",
    ),
    "VM_STOPPED_BILLING_EXTENDED": _spec(
        "stopped_not_deallocated",
        signals=(SignalDef("Power state", "power_state", threshold_literal="deallocated", comparator="neq"),),
        summary="VM is stopped but not deallocated — compute charges may still apply.",
        savings_method="full_monthly_cost",
    ),
    "VM_SKU_SIZING_EXTENDED": _spec(
        "vm_sku_rightsizing",
        signals=(
            _cpu_signal("cpu_threshold_pct", 25),
            SignalDef("Memory utilization", "avg_memory_pct", threshold_key="memory_idle_pct", comparator="lte", format_value=_fmt_pct),
            SignalDef("Sizing action", "sizing_action", threshold_literal="downgrade or cross_family", comparator="not_empty"),
            SignalDef("Suggested SKU", "suggested_sku", comparator="not_empty"),
        ),
        summary="VM {vm_size} ({family_label}) — consider {suggested_sku} ({sizing_action}).",
        savings_method="azure_retail_sku_diff",
    ),
    "VM_UNDERUTILIZED_EXTENDED": _spec(
        "underutilized_cpu",
        signals=(_cpu_signal("cpu_threshold_pct", 5),),
        summary="VM average CPU is {avg_cpu_pct:.1f}% (extended idle analysis).",
        savings_method="azure_retail_sku_diff",
    ),
    "VM_RIGHTSIZE_FAMILY": _spec(
        "cross_family_candidate",
        signals=(
            SignalDef("Suggested SKU", "suggested_sku", comparator="not_empty"),
            SignalDef("Suggested family", "suggested_family", comparator="not_empty"),
        ),
        summary="VM {vm_size} ({family_label}) — consider {suggested_sku} ({sizing_action}).",
        savings_method="azure_retail_sku_diff",
        savings_factor_key="min_rightsize_savings_pct",
    ),
    "VM_COMMITMENT_CANDIDATE": _spec(
        "commitment_candidate",
        signals=(
            SignalDef("Monthly cost", "monthly_cost_usd", threshold_key="min_monthly_savings_usd", comparator="gte", format_value=_fmt_money),
            SignalDef("Uptime hours", "uptime_hours", threshold_key="vm_uptime_hours_candidate", comparator="gte"),
        ),
        summary="VM has sustained usage suitable for reserved capacity or savings plan.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.35,
    ),
    "VM_MISSING_GOVERNANCE_TAGS": _spec(
        "missing_required_tags",
        signals=(SignalDef("Missing tags", "missing_tags", threshold_literal="none", comparator="empty"),),
        summary="Resource is missing required governance tags: {missing_tags}.",
        savings_method="governance",
    ),
    "SPOT_OPPORTUNITY": _spec(
        "spot_eligible_env",
        signals=(
            SignalDef("Environment tag", "environment", comparator="not_empty"),
            SignalDef("Pricing model", "pricing_model", threshold_literal="Spot", comparator="neq"),
        ),
        summary="VM in non-prod environment '{environment}' runs on on-demand pricing.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.85,
    ),
    # ── Disks ──────────────────────────────────────────────────────────────
    "DISK_UNATTACHED": _spec(
        "disk_unattached",
        signals=(SignalDef("Disk state", "disk_state", threshold_literal="Attached", comparator="neq"),),
        summary="Managed disk state is '{disk_state}' ({size_gb} GB, {sku}).",
        savings_method="full_monthly_cost",
    ),
    "DISK_OVERSIZE": _spec(
        "premium_unattached",
        signals=(
            SignalDef("Disk state", "disk_state", threshold_literal="Unattached", comparator="eq"),
            SignalDef("Disk SKU", "sku", threshold_literal="Premium", comparator="contains"),
        ),
        summary="Unattached Premium disk — downgrade to Standard SSD to reduce cost.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.70,
    ),
    "DISK_UNUSED_EXTENDED": _spec(
        "disk_unattached",
        signals=(SignalDef("Disk state", "disk_state", threshold_literal="Attached", comparator="neq"),),
        summary="Managed disk is not attached to a VM.",
        savings_method="full_monthly_cost",
    ),
    "DISK_OVERSIZE_EXTENDED": _spec(
        "premium_idle_io",
        signals=(
            SignalDef("Disk state", "disk_state", threshold_literal="Attached", comparator="eq"),
            SignalDef("Disk SKU", "sku", threshold_literal="Premium", comparator="contains"),
            SignalDef("Combined disk I/O", "disk_read_bps", threshold_key="disk_io_idle_bps", comparator="lte"),
            SignalDef("IOPS utilization", "disk_iops_utilization_pct", threshold_key="disk_iops_block_downgrade_pct", comparator="lt"),
        ),
        summary="Attached Premium disk with near-zero I/O ({size_gb} GB, {sku}).",
        savings_method="azure_retail_sku_diff",
    ),
    "DISK_UNDERPROVISIONED": _spec(
        "disk_high_iops",
        signals=(
            SignalDef("Disk state", "disk_state", threshold_literal="Attached", comparator="eq"),
            SignalDef("IOPS utilization", "disk_iops_utilization_pct", threshold_key="disk_iops_high_util_pct", comparator="gte"),
        ),
        summary="Disk IOPS or throughput is near the provisioned cap ({disk_iops_utilization_pct}% of {provisioned_iops} IOPS).",
        savings_method="governance",
    ),
    "SNAPSHOT_OLD": _spec(
        "snapshot_stale",
        signals=(
            SignalDef("Snapshot age", "age_days", threshold_key="snapshot_retention_days", comparator="gte"),
            SignalDef("Size", "size_gb", threshold_key="snapshot_min_size_gb", comparator="gte"),
        ),
        summary="Snapshot is {age_days} days old ({size_gb} GB).",
        savings_method="full_monthly_cost",
    ),
    "SNAPSHOT_RETENTION_EXTENDED": _spec(
        "snapshot_stale",
        signals=(
            SignalDef("Snapshot age", "age_days", threshold_key="snapshot_retention_days", comparator="gte"),
            SignalDef("Size", "size_gb", threshold_key="snapshot_min_size_gb", comparator="gte"),
            SignalDef("Monthly cost", "monthly_cost_usd", threshold_key="min_monthly_savings_usd", comparator="gte"),
        ),
        summary="Snapshot exceeds retention policy at {age_days} days ({size_gb} GB).",
        savings_method="full_monthly_cost",
    ),
    # ── App Service ────────────────────────────────────────────────────────
    "ASP_EMPTY": _spec(
        "empty_plan",
        signals=(SignalDef("Hosted apps", "app_count", threshold_literal="1", comparator="gte"),),
        summary="App Service Plan hosts {app_count} app(s).",
        savings_method="full_monthly_cost",
    ),
    "ASP_OVERPROVISIONED": _spec(
        "premium_underutilized",
        signals=(
            SignalDef("Plan tier", "tier", comparator="not_empty"),
            SignalDef("Hosted apps", "app_count", threshold_literal="< 2", comparator="lt"),
        ),
        summary="Plan tier {tier} hosts only {app_count} app(s).",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.35,
    ),
    "PLAN_UNDERUTILIZED": _spec(
        "plan_underutilized",
        signals=(
            SignalDef("CPU utilization", "cpu_pct", threshold_key="cpu_oversize_threshold_pct",
                      threshold_literal="≤ 20%", comparator="lte", format_value=_fmt_pct),
            SignalDef("Memory utilization", "memory_pct", threshold_key="mem_idle_pct",
                      threshold_literal="≤ 30%", comparator="lte", format_value=_fmt_pct, optional=True),
            SignalDef("Plan tier", "tier", comparator="not_empty"),
        ),
        summary="App Service Plan tier {tier} is underutilized (CPU {cpu_pct:.1f}%, memory {memory_pct:.1f}%).",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.35,
    ),
    "APP_IDLE": _spec(
        "idle_webapp",
        signals=(
            SignalDef("Request count", "request_count", threshold_key="app_idle_request_threshold", comparator="lte"),
            SignalDef("App state", "state", threshold_literal="Running", comparator="eq"),
        ),
        summary="Web app state is '{state}' with low request volume ({request_count} requests).",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.50,
    ),
    "APP_SERVICE_PLAN_EXTENDED": _spec(
        "premium_underutilized",
        signals=(
            SignalDef("Plan tier", "tier", comparator="not_empty"),
            SignalDef("Hosted apps", "app_count", threshold_key="asp_min_apps_for_premium", comparator="lt"),
        ),
        summary="App Service Plan tier {tier} with {app_count} app(s).",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.35,
    ),
    "WEBAPP_STOPPED_EXTENDED": _spec(
        "webapp_stopped",
        signals=(SignalDef("App state", "state", threshold_literal="Running", comparator="neq"),),
        summary="Web app state is '{state}'.",
        savings_method="full_monthly_cost",
    ),
    "WEBAPP_ALWAYS_ON_EXTENDED": _spec(
        "always_on_nonprod",
        signals=(
            SignalDef("Always On", "alwaysOn", threshold_literal="false for non-prod", comparator="truthy"),
            SignalDef("Environment", "environment", comparator="not_empty"),
        ),
        summary="Always On enabled on non-prod app (env={environment}).",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.20,
    ),
    # ── AKS ────────────────────────────────────────────────────────────────
    "AKS_NODE_IDLE": _spec(
        "idle_nodes",
        signals=(
            SignalDef("Idle nodes", "idle_nodes", threshold_literal="0", comparator="gt"),
            SignalDef(
                "Cluster CPU utilization",
                "cluster_cpu_pct",
                threshold_key="node_cpu_idle_pct",
                comparator="lte",
                format_value=_fmt_pct,
                optional=True,
            ),
            SignalDef(
                "Cluster memory utilization",
                "cluster_mem_pct",
                threshold_key="node_mem_idle_pct",
                comparator="lte",
                format_value=_fmt_pct,
                optional=True,
            ),
        ),
        summary="{idle_nodes} idle nodes in pool '{pool_name}' based on utilization metrics.",
        savings_method="per_unit",
        savings_desc="Estimated savings = idle node count × per-node monthly cost share.",
        data_source="azure_monitor",
    ),
    "AKS_OVERPROVISIONED": _spec(
        "idle_nodes",
        signals=(
            SignalDef("Idle nodes", "idle_nodes", threshold_literal="0", comparator="gt"),
            SignalDef(
                "Cluster CPU utilization",
                "cluster_cpu_pct",
                threshold_key="node_cpu_downsize_pct",
                comparator="lte",
                format_value=_fmt_pct,
                optional=True,
            ),
            SignalDef(
                "Cluster memory utilization",
                "cluster_mem_pct",
                threshold_key="node_memory_pressure_pct",
                comparator="lte",
                format_value=_fmt_pct,
                optional=True,
            ),
        ),
        summary="Cluster has {idle_nodes} idle nodes that can be scaled down.",
        savings_method="per_unit",
        data_source="azure_monitor",
    ),
    "AKS_DEV_RUNNING_NIGHTS": _spec(
        "nonprod_24x7",
        signals=(SignalDef("Environment", "environment", comparator="not_empty"),),
        summary="Non-prod cluster (env={environment}) runs continuously.",
        savings_method="factor_of_monthly_cost",
        savings_factor=14 / 24,
        savings_desc="Assumes start/stop schedule saves ~14 hours per day of node cost.",
    ),
    "AKS_NO_SPOT": _spec(
        "on_demand_node_pool",
        signals=(SignalDef("Node priority", "scale_set_priority", threshold_literal="Spot", comparator="neq"),),
        summary="Node pool uses on-demand VMs instead of Spot.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.80,
    ),
    "AKS_OLD_VERSION": _spec(
        "unsupported_k8s",
        signals=(
            SignalDef("Kubernetes version", "kubernetes_version", comparator="not_empty"),
            SignalDef("Supported versions", "supported_versions", comparator="not_empty", optional=True),
        ),
        summary="Cluster runs Kubernetes {kubernetes_version} outside supported versions.",
        savings_method="governance",
    ),
    "AKS_NO_AUTOSCALER": _spec(
        "autoscaler_disabled",
        signals=(
            SignalDef("Cluster autoscaler", "autoscaler_enabled", threshold_literal="enabled", comparator="falsy"),
            SignalDef(
                "Cluster CPU utilization",
                "cluster_cpu_pct",
                threshold_key="node_cpu_downsize_pct",
                comparator="lte",
                format_value=_fmt_pct,
                optional=True,
            ),
        ),
        summary="Pool '{pool_name}' runs without cluster autoscaler despite low utilization.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.30,
        data_source="azure_monitor",
    ),
    "AKS_SINGLE_NODE_POOL": _spec(
        "single_pool",
        signals=(SignalDef("Node pool count", "pool_count", threshold_literal="≥ 2", comparator="lt"),),
        summary="Cluster has only {pool_count} node pool.",
        savings_method="governance",
    ),
    "AKS_EMPTY_POOL": _spec(
        "empty_node_pool",
        signals=(
            SignalDef("Node count", "node_count", threshold_key="node_count_min", comparator="lte"),
            SignalDef("Node pool count", "pool_count", comparator="not_empty", optional=True),
        ),
        summary="Node pool has {node_count} nodes (empty or below minimum threshold).",
        savings_method="full_monthly_cost",
    ),
    "AKS_IDLE_POOL_EXTENDED": _spec(
        "idle_pool",
        signals=(
            SignalDef("Idle node ratio", "idle_node_ratio", threshold_key="aks_max_idle_node_ratio", comparator="gte"),
            SignalDef(
                "Cluster CPU utilization",
                "cluster_cpu_pct",
                threshold_key="node_cpu_idle_pct",
                comparator="lte",
                format_value=_fmt_pct,
                optional=True,
            ),
            SignalDef(
                "Cluster memory utilization",
                "cluster_mem_pct",
                threshold_key="node_mem_idle_pct",
                comparator="lte",
                format_value=_fmt_pct,
                optional=True,
            ),
        ),
        summary="AKS pool has high idle node ratio ({idle_node_ratio:.0%}).",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.30,
        data_source="azure_monitor",
    ),
    "AKS_NONPROD_SCHEDULING": _spec(
        "nonprod_24x7",
        signals=(SignalDef("Environment", "environment", comparator="not_empty"),),
        summary="Non-prod AKS cluster should use scheduled start/stop.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.40,
    ),
    "AKS_SYSTEM_POOL_RELIABILITY": _spec(
        "system_pool_too_small",
        signals=(SignalDef("System pool nodes", "system_pool_count", threshold_key="aks_min_system_nodes", comparator="lt"),),
        summary="System node pool has {system_pool_count} nodes (minimum recommended: {aks_min_system_nodes}).",
        savings_method="governance",
    ),
    # ── Storage ──────────────────────────────────────────────────────────
    "STORAGE_HOT_UNUSED": _spec(
        "hot_tier_review",
        signals=(SignalDef("Access tier", "access_tier", threshold_literal="Hot", comparator="eq", format_value=_fmt_storage_tier),),
        summary="Storage account access tier is Hot — verify active access patterns.",
        savings_method="governance",
    ),
    "STORAGE_HOT_UNUSED_EXTENDED": _spec(
        "hot_tier_review",
        signals=(SignalDef("Access tier", "access_tier", threshold_literal="Hot", comparator="eq", format_value=_fmt_storage_tier),),
        summary="Storage account access tier is Hot — verify active access patterns.",
        savings_method="governance",
    ),
    "STORAGE_NO_LIFECYCLE": _spec(
        "no_lifecycle_policy",
        signals=(SignalDef("Lifecycle policy", "has_lifecycle_policy", threshold_literal="configured", comparator="falsy", optional=True),),
        summary="No lifecycle management policy verified for this storage account.",
        savings_method="governance",
    ),
    "STORAGE_LRS_CRITICAL": _spec(
        "lrs_critical_data",
        signals=(SignalDef("Redundancy SKU", "sku", threshold_literal="GRS/GZRS", comparator="neq", format_value=_fmt_storage_sku),),
        summary="Critical data may need geo-redundant storage (current SKU: {sku_display}).",
        savings_method="governance",
    ),
    "STORAGE_LRS_CRITICAL_EXTENDED": _spec(
        "lrs_critical_data",
        signals=(SignalDef("Redundancy SKU", "sku", threshold_literal="GRS/GZRS", comparator="neq", format_value=_fmt_storage_sku),),
        summary="Production storage uses locally redundant SKU {sku_display}.",
        savings_method="governance",
    ),
    "STORAGE_LIFECYCLE_EXTENDED": _spec(
        "lifecycle_candidate",
        signals=(
            SignalDef("Monthly transactions", "transaction_count", threshold_key="storage_transaction_low", comparator="lt", format_value=_fmt_storage_transactions, optional=True),
            SignalDef("Used capacity", "used_capacity_bytes", threshold_key="storage_utilization_low_pct", comparator="review", format_value=_fmt_storage_bytes, optional=True),
        ),
        summary="Add lifecycle rules to move cold data to Cool or Archive tiers.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.25,
    ),
    "STORAGE_REDUNDANCY_EXTENDED": _spec(
        "geo_redundant_nonprod",
        signals=(
            SignalDef("Redundancy SKU", "sku", comparator="not_empty", format_value=_fmt_storage_sku),
            SignalDef("Environment", "environment", comparator="not_empty"),
        ),
        summary="Non-prod storage uses geo-redundant SKU {sku_display}.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.50,
    ),
    "STORAGE_EGRESS_HIGH_EXTENDED": _spec(
        "high_egress",
        signals=(SignalDef("Monthly egress", "egress_bytes", threshold_key="storage_egress_bytes_monthly", comparator="gte", format_value=_fmt_storage_bytes),),
        summary="Storage egress exceeds the monthly review threshold.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.20,
    ),
    "STORAGE_COOL_TIER_CANDIDATE_EXTENDED": _spec(
        "cool_tier_candidate",
        signals=(
            SignalDef("Access tier", "access_tier", threshold_literal="Hot", comparator="eq", format_value=_fmt_storage_tier),
            SignalDef("Monthly transactions", "transaction_count", threshold_key="storage_transaction_low", comparator="lt", format_value=_fmt_storage_transactions),
        ),
        summary="Hot tier storage with low activity is a Cool tier migration candidate.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.50,
    ),
    # ── Network ──────────────────────────────────────────────────────────
    "IP_UNASSOCIATED": _spec(
        "ip_unassociated",
        signals=(SignalDef("IP association", "allocation", threshold_literal="associated", comparator="eq"),),
        summary="Static public IP is not associated with a NIC or load balancer frontend.",
        savings_method="full_monthly_cost",
    ),
    "PUBLIC_IP_IDLE_EXTENDED": _spec(
        "ip_unassociated",
        signals=(SignalDef("IP association", "allocation", threshold_literal="associated", comparator="eq"),),
        summary="Public IP appears idle or unassociated.",
        savings_method="full_monthly_cost",
    ),
    "NIC_UNATTACHED": _spec(
        "nic_orphaned",
        signals=(SignalDef("Attached to VM", "has_vm", threshold_literal="yes", comparator="falsy"),),
        summary="Network interface is not attached to a VM or private endpoint.",
        savings_method="governance",
    ),
    "NIC_ORPHANED_EXTENDED": _spec(
        "nic_orphaned",
        signals=(SignalDef("Attached to VM", "has_vm", threshold_literal="yes", comparator="falsy"),),
        summary="Orphaned network interface with no compute attachment.",
        savings_method="governance",
    ),
    "NAT_GATEWAY_IDLE": _spec(
        "nat_no_subnets",
        signals=(SignalDef("Associated subnets", "subnet_count", threshold_literal="≥ 1", comparator="lt"),),
        summary="NAT Gateway has {subnet_count} associated subnet(s).",
        savings_method="full_monthly_cost",
    ),
    "NAT_GATEWAY_IDLE_EXTENDED": _spec(
        "nat_no_subnets",
        signals=(SignalDef("Associated subnets", "subnet_count", threshold_literal="≥ 1", comparator="lt"),),
        summary="NAT Gateway has no subnet associations.",
        savings_method="full_monthly_cost",
    ),
    "LB_NO_BACKEND": _spec(
        "lb_idle_no_backends",
        signals=(SignalDef("Backend pools with targets", "all_backends_empty", threshold_literal="false", comparator="falsy"),),
        summary="Load balancer has {backend_pool_count} pool(s) with no active backend instances.",
        savings_method="full_monthly_cost",
    ),
    "LOAD_BALANCER_IDLE_EXTENDED": _spec(
        "lb_idle_no_backends",
        signals=(SignalDef("Backend pools with targets", "all_backends_empty", threshold_literal="false", comparator="falsy"),),
        summary="Load balancer backends are empty.",
        savings_method="full_monthly_cost",
    ),
    "LOAD_BALANCER_SNAT_PRESSURE": _spec(
        "snat_pressure",
        signals=(SignalDef("SNAT port usage %", "snat_port_usage_pct", threshold_key="lb_snat_pressure_pct", comparator="gte", format_value=_fmt_pct),),
        summary="Load balancer SNAT port utilization exceeds safe threshold.",
        savings_method="governance",
    ),
    "LOAD_BALANCER_THROUGHPUT_RIGHTSIZE": _spec(
        "throughput_rightsize",
        signals=(SignalDef("Avg vs peak bytes %", "byte_count", threshold_key="lb_throughput_low_pct_of_peak", comparator="lt", format_value=_fmt_pct),),
        summary="Sustained load balancer throughput is far below peak.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.30,
    ),
    "LOAD_BALANCER_BACKEND_CONSOLIDATION": _spec(
        "low_traffic",
        signals=(SignalDef("Byte count", "byte_count", threshold_key="lb_idle_byte_threshold", comparator="lt"),),
        summary="Load balancer has backends but very low traffic.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.50,
    ),
    "LOAD_BALANCER_BASIC_SKU_MIGRATION": _spec(
        "basic_sku_migration",
        signals=(SignalDef("SKU", "sku_name", threshold_literal="Basic", comparator="eq"),),
        summary="Basic load balancer SKU is retiring — migrate to Standard.",
        savings_method="governance",
    ),
    "PUBLIC_IP_BASIC_SKU_MIGRATION": _spec(
        "basic_sku_migration",
        signals=(SignalDef("SKU", "sku_name", threshold_literal="Basic", comparator="eq"),),
        summary="Basic public IP SKU is retiring — migrate to Standard.",
        savings_method="governance",
    ),
    "NAT_GATEWAY_SNAT_EXHAUSTION": _spec(
        "snat_exhaustion",
        signals=(SignalDef("SNAT utilization %", "snat_utilization_pct", threshold_key="nat_snat_exhaustion_pct", comparator="gte", format_value=_fmt_pct),),
        summary="NAT Gateway SNAT utilization exceeds safe threshold.",
        savings_method="governance",
    ),
    "NAT_GATEWAY_SKU_V2_UPGRADE": _spec(
        "sku_v2_candidate",
        signals=(SignalDef("Throughput (Gbps)", "throughput_gbps", threshold_key="nat_throughput_v2_upgrade_gbps", comparator="gte"),),
        summary="NAT Gateway throughput may require StandardV2 SKU.",
        savings_method="governance",
    ),
    "NAT_GATEWAY_SUBNET_CONSOLIDATION": _spec(
        "subnet_consolidation",
        signals=(
            SignalDef("Public IP count", "public_ip_count", threshold_literal="1", comparator="gt"),
            SignalDef("Subnet count", "subnet_count", threshold_literal="1", comparator="gt"),
        ),
        summary="NAT Gateway has multiple IPs and subnets with low traffic.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.25,
    ),
    "APPGW_UNUSED": _spec(
        "idle_no_listeners",
        signals=(SignalDef("HTTP listeners configured", "http_listener_count", threshold_literal="1", comparator="gte"),),
        summary="Application Gateway has no HTTP listeners — it cannot route traffic and is treated as idle.",
        savings_method="full_monthly_cost",
        data_source="synced_inventory",
    ),
    "APP_GATEWAY_IDLE_EXTENDED": _spec(
        "idle_no_listeners",
        signals=(SignalDef("HTTP listeners configured", "http_listener_count", threshold_literal="1", comparator="gte"),),
        summary="Application Gateway has no HTTP listeners — it cannot route traffic and is treated as idle.",
        savings_method="full_monthly_cost",
        data_source="synced_inventory",
    ),
    "NSG_ORPHANED_EXTENDED": _spec(
        "nsg_unassociated",
        signals=(
            SignalDef("Associated subnets", "subnet_count", threshold_literal="0", comparator="eq"),
            SignalDef("Associated NICs", "nic_count", threshold_literal="0", comparator="eq"),
        ),
        summary="NSG is not associated with subnets or NICs.",
        savings_method="governance",
    ),
    "NSG_PERMISSIVE_EXTENDED": _spec(
        "permissive_rules",
        signals=(SignalDef("Risky rules", "risky_rule_count", threshold_literal="0", comparator="gt"),),
        summary="NSG contains permissive inbound rules that increase attack surface.",
        savings_method="governance",
    ),
    "PRIVATE_DNS_EMPTY_EXTENDED": _spec(
        "empty_dns_zone",
        signals=(
            SignalDef(
                "Record sets",
                "record_set_count",
                threshold_key="private_dns_max_default_record_sets",
                comparator="gt",
            ),
        ),
        summary="Private DNS zone only contains default SOA/NS records ({record_set_count} record sets).",
        savings_method="full_monthly_cost",
        data_source="synced_inventory",
    ),
    # ── Database ─────────────────────────────────────────────────────────
    "REDIS_FAILED": _spec(
        "provisioning_failed",
        signals=(SignalDef("Provisioning state", "provisioning_state", threshold_literal="Succeeded", comparator="neq"),),
        summary="Redis cache provisioning state is '{provisioning_state}'.",
        savings_method="governance",
    ),
    "REDIS_OVERSIZED": _spec(
        "premium_oversized",
        signals=(
            SignalDef("SKU tier", "tier", threshold_literal="Premium", comparator="contains"),
            SignalDef("Capacity", "capacity", comparator="not_empty"),
        ),
        summary="Redis Premium capacity {capacity} may exceed workload needs.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.35,
    ),
    "REDIS_HEALTH_EXTENDED": _spec(
        "provisioning_failed",
        signals=(SignalDef("Provisioning state", "state", threshold_literal="Succeeded", comparator="neq"),),
        summary="Redis instance health requires attention (state={state}).",
        savings_method="governance",
    ),
    "REDIS_RIGHTSIZE_EXTENDED": _spec(
        "premium_oversized",
        signals=(SignalDef("Capacity", "capacity", threshold_key="redis_premium_min_capacity", comparator="gte"),),
        summary="Redis capacity {capacity} exceeds recommended minimum.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.35,
    ),
    "REDIS_IDLE_DETECTION": _spec(
        "idle_zero_ops",
        signals=(SignalDef("Operations per second", "ops_per_sec", threshold_key="redis_idle_ops_threshold", comparator="lte"),),
        summary="Redis cache shows zero operations per second in Azure Monitor.",
        savings_method="full_monthly_cost",
    ),
    "REDIS_MEMORY_PRESSURE": _spec(
        "memory_pressure",
        signals=(
            SignalDef("Memory utilization", "memory_pct", threshold_key="redis_memory_pressure_pct", comparator="gte", format_value=_fmt_pct),
            SignalDef("Evicted keys", "evicted_keys", comparator="gt", threshold_literal="0"),
        ),
        summary="Redis memory pressure or evictions require upgrade or policy review.",
        savings_method="governance",
    ),
    "REDIS_LOW_UTILIZATION": _spec(
        "low_utilization",
        signals=(
            SignalDef("Memory utilization", "memory_pct", threshold_key="redis_low_utilization_pct", comparator="lte", format_value=_fmt_pct),
            SignalDef("Server load", "server_load_pct", threshold_key="redis_server_load_low_pct", comparator="lte", format_value=_fmt_pct),
        ),
        summary="Redis memory and server load are consistently low.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.35,
    ),
    "REDIS_HIT_RATIO_POOR": _spec(
        "poor_hit_ratio",
        signals=(SignalDef("Cache hit rate", "cache_hit_rate_pct", threshold_key="redis_hit_ratio_poor_pct", comparator="lte", format_value=_fmt_pct),),
        summary="Redis cache hit ratio is below the healthy threshold.",
        savings_method="governance",
    ),
    "REDIS_CLUSTER_UNNECESSARY": _spec(
        "cluster_unnecessary",
        signals=(
            SignalDef("Shard count", "shard_count", comparator="lte", threshold_literal="1"),
            SignalDef("Operations per second", "ops_per_sec", threshold_key="redis_cluster_ops_threshold", comparator="lte"),
        ),
        summary="Single-shard Premium Redis with low throughput may not need clustering.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.35,
    ),
    "REDIS_PERSISTENCE_REVIEW": _spec(
        "persistence_review",
        signals=(SignalDef("Persistence enabled", "persistence_enabled", comparator="eq", threshold_literal="true"),),
        summary="Redis persistence (RDB/AOF) is enabled — review durability vs. storage cost.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.10,
    ),
    "REDIS_TIER_REVIEW": _spec(
        "tier_shard_review",
        signals=(
            SignalDef("Capacity", "capacity", threshold_key="redis_premium_min_capacity", comparator="gte"),
            SignalDef("Shard count", "shard_count", comparator="gt", threshold_literal="1"),
        ),
        summary="Redis tier, shard count, or eviction policy may exceed workload needs.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.35,
    ),
    "SQL_IDLE": _spec(
        "sql_underutilized",
        signals=(SignalDef("DTU/CPU utilization", "dtu_pct", threshold_key="db_dtu_idle_pct", comparator="lte", format_value=_fmt_pct),),
        summary="SQL database utilization is below idle threshold.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.50,
    ),
    "SQL_NO_SERVERLESS": _spec(
        "provisioned_not_serverless",
        signals=(SignalDef("Compute tier", "tier", threshold_literal="Serverless", comparator="neq"),),
        summary="SQL DB uses provisioned tier {tier}/{sku} instead of serverless.",
        savings_method="governance",
    ),
    "SQL_SERVERLESS_EXTENDED": _spec(
        "serverless_candidate",
        signals=(SignalDef("CPU utilization", "cpu_pct", threshold_key="sql_serverless_candidate_cpu_pct", comparator="lte", format_value=_fmt_pct),),
        summary="SQL database is a candidate for serverless auto-pause.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.40,
    ),
    "COSMOS_PROVISIONED": _spec(
        "provisioned_throughput",
        signals=(SignalDef("Serverless enabled", "serverless_enabled", threshold_literal="true", comparator="falsy"),),
        summary="Cosmos DB uses provisioned throughput instead of serverless/autoscale.",
        savings_method="governance",
    ),
    "COSMOS_AUTOSCALE_EXTENDED": _spec(
        "autoscale_candidate",
        signals=(SignalDef("Utilization", "utilization_pct", threshold_key="cosmos_autoscale_candidate_utilization_pct", comparator="lte", format_value=_fmt_pct),),
        summary="Cosmos DB utilization supports autoscale or serverless migration.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.30,
    ),
    "COSMOS_SERVERLESS": _spec(
        "serverless_candidate",
        signals=(SignalDef("Total RU (7d)", "total_ru", threshold_key="cosmos_serverless_ru_threshold", comparator="lt"),),
        summary="Cosmos DB RU consumption supports serverless migration.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.35,
    ),
    "COSMOS_RU_RIGHT_SIZING_UNDER": _spec(
        "ru_underutilized",
        signals=(SignalDef("Normalized RU %", "normalized_ru_pct", threshold_key="cosmos_ru_low_pct", comparator="lt", format_value=_fmt_pct),),
        summary="Cosmos DB normalized RU consumption is below the downscale threshold.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.35,
    ),
    "COSMOS_RU_RIGHT_SIZING_OVER": _spec(
        "ru_overutilized",
        signals=(SignalDef("Normalized RU %", "normalized_ru_pct", threshold_key="cosmos_ru_high_pct", comparator="gte", format_value=_fmt_pct),),
        summary="Cosmos DB normalized RU consumption exceeds the upscale threshold.",
        savings_method="governance",
    ),
    "COSMOS_THROTTLING_DETECTED": _spec(
        "throttling_risk",
        signals=(SignalDef("Normalized RU %", "normalized_ru_peak_pct", threshold_key="cosmos_throttle_ru_pct", comparator="gte", format_value=_fmt_pct),),
        summary="Cosmos DB normalized RU consumption indicates throttling risk.",
        savings_method="governance",
    ),
    "COSMOS_HOT_CONTAINER_DETECTED": _spec(
        "hot_partition",
        signals=(SignalDef("RU skew ratio", "ru_skew_ratio", threshold_key="cosmos_hot_partition_skew_ratio", comparator="gte"),),
        summary="Cosmos DB RU consumption is uneven across partitions.",
        savings_method="governance",
    ),
    "COSMOS_API_COST_VARIANCE": _spec(
        "api_premium",
        signals=(SignalDef("API type", "api_type", comparator="not_empty"),),
        summary="Cosmos DB API type may carry higher RU cost than SQL API.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.15,
    ),
    "COSMOS_CONSISTENCY_OVERPROVISIONED": _spec(
        "consistency_review",
        signals=(SignalDef("Consistency level", "consistency_level", comparator="not_empty"),),
        summary="Cosmos DB consistency level increases RU cost.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.25,
    ),
    "COSMOS_LARGE_ITEMS_DETECTED": _spec(
        "large_items",
        signals=(SignalDef("Average item size", "avg_item_bytes", threshold_key="cosmos_large_item_bytes", comparator="gte"),),
        summary="Cosmos DB average item size is large.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.15,
    ),
    "COSMOS_INDEXING_OVERPROVISIONED": _spec(
        "index_overprovisioned",
        signals=(SignalDef("Index to data ratio", "index_to_data_ratio", threshold_key="cosmos_index_to_data_ratio", comparator="gte"),),
        summary="Cosmos DB index size is high relative to data.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.20,
    ),
    "COSMOS_MULTI_WRITE_UNNECESSARY": _spec(
        "multi_write_review",
        signals=(SignalDef("Multi-write enabled", "multi_write_enabled", threshold_literal="true", comparator="eq"),),
        summary="Cosmos DB multi-region writes may be unnecessary.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.30,
    ),
    "COSMOS_FAILOVER_UNNECESSARY": _spec(
        "failover_review",
        signals=(SignalDef("Automatic failover", "automatic_failover_enabled", threshold_literal="true", comparator="eq"),),
        summary="Cosmos DB automatic failover may be unnecessary for non-production.",
        savings_method="governance",
    ),
    "COSMOS_FREE_TIER_SUBOPTIMAL": _spec(
        "free_tier_review",
        signals=(SignalDef("Free tier", "free_tier_enabled", threshold_literal="true", comparator="eq"),),
        summary="Cosmos DB free tier usage exceeds included capacity.",
        savings_method="governance",
    ),
    "COSMOS_RESERVED_CAPACITY_ELIGIBLE": _spec(
        "reserved_capacity_candidate",
        signals=(SignalDef("Normalized RU %", "normalized_ru_pct", threshold_key="cosmos_ru_low_pct", comparator="gte", format_value=_fmt_pct),),
        summary="Cosmos DB stable RU utilization supports reserved capacity.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.38,
    ),
    "POSTGRESQL_STOPPED_EXTENDED": _spec(
        "postgres_stopped_billed",
        signals=(SignalDef("Server state", "state", threshold_literal="Ready", comparator="neq"),),
        summary="PostgreSQL flexible server state is '{state}'.",
        savings_method="full_monthly_cost",
    ),
    "POSTGRESQL_BURSTABLE_EXTENDED": _spec(
        "burstable_candidate",
        signals=(SignalDef("SKU tier", "sku", comparator="not_empty"),),
        summary="Non-prod PostgreSQL may use Burstable SKU.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.35,
    ),
    "POSTGRESQL_STORAGE_EXTENDED": _spec(
        "storage_oversized",
        signals=(SignalDef("Storage (GB)", "storage_gb", comparator="not_empty"),),
        summary="PostgreSQL storage allocation is {storage_gb} GB.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.20,
    ),
    "POSTGRESQL_LOW_COMPUTE_UTILIZATION": _spec(
        "low_compute",
        signals=(
            SignalDef("CPU utilization", "cpu_pct", threshold_key="postgresql_cpu_low_pct", comparator="lt", format_value=_fmt_pct),
            SignalDef("Memory utilization", "memory_pct", threshold_key="postgresql_memory_low_pct", comparator="lt", format_value=_fmt_pct),
        ),
        summary="PostgreSQL shows sustained low CPU and memory utilization.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.35,
    ),
    "POSTGRESQL_HIGH_COMPUTE_DEMAND": _spec(
        "high_cpu",
        signals=(SignalDef("CPU utilization", "cpu_pct", threshold_key="postgresql_cpu_high_pct", comparator="gte", format_value=_fmt_pct),),
        summary="PostgreSQL CPU exceeds the high utilization threshold.",
        savings_method="governance",
    ),
    "POSTGRESQL_MEMORY_PRESSURE": _spec(
        "memory_pressure",
        signals=(SignalDef("Memory utilization", "memory_pct", threshold_key="postgresql_memory_pressure_pct", comparator="gte", format_value=_fmt_pct),),
        summary="PostgreSQL memory utilization is elevated in Azure Monitor.",
        savings_method="governance",
    ),
    "POSTGRESQL_STORAGE_EXPANSION": _spec(
        "storage_expansion",
        signals=(SignalDef("Storage utilization", "storage_pct", threshold_key="postgresql_storage_high_pct", comparator="gte", format_value=_fmt_pct),),
        summary="PostgreSQL storage utilization is high.",
        savings_method="governance",
    ),
    "POSTGRESQL_IOPS_PRESSURE": _spec(
        "iops_pressure",
        signals=(SignalDef("Disk IOPS consumed", "disk_iops_pct", threshold_key="postgresql_iops_pressure_pct", comparator="gte", format_value=_fmt_pct),),
        summary="PostgreSQL disk IOPS consumption is near limits.",
        savings_method="governance",
    ),
    "POSTGRESQL_CONNECTION_POOL_RISK": _spec(
        "connection_pool_risk",
        signals=(SignalDef("Active connections", "active_connections", threshold_key="postgresql_connection_risk_absolute", comparator="gte"),),
        summary="PostgreSQL concurrent connections are high.",
        savings_method="governance",
    ),
    "POSTGRESQL_HA_UNNECESSARY": _spec(
        "ha_unnecessary",
        signals=(SignalDef("HA mode", "ha_mode", comparator="not_empty"),),
        summary="PostgreSQL HA is enabled in a non-production environment.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.33,
    ),
    "POSTGRESQL_HA_REQUIRED": _spec(
        "ha_required",
        signals=(SignalDef("HA mode", "ha_mode", comparator="not_empty"),),
        summary="Production PostgreSQL server does not have HA enabled.",
        savings_method="governance",
    ),
    "POSTGRESQL_READ_REPLICA_ANALYSIS": _spec(
        "read_replica_review",
        signals=(SignalDef("Replication lag (sec)", "replication_lag_sec", threshold_key="postgresql_replication_lag_seconds", comparator="gt"),),
        summary="PostgreSQL read replica cost and lag should be reviewed.",
        savings_method="full_monthly_cost",
    ),
    "POSTGRESQL_VERSION_OUTDATED": _spec(
        "version_outdated",
        signals=(SignalDef("Version", "version", comparator="not_empty"),),
        summary="PostgreSQL major version is behind supported releases.",
        savings_method="governance",
    ),
    "POSTGRESQL_BACKUP_RETENTION_REVIEW": _spec(
        "backup_retention_review",
        signals=(SignalDef("Backup retention (days)", "backup_retention_days", comparator="not_empty"),),
        summary="PostgreSQL backup retention exceeds typical targets.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.10,
    ),
    # ── Containers / ACR ───────────────────────────────────────────────────
    "ACR_PREMIUM_EXTENDED": _spec(
        "premium_nonprod",
        signals=(
            SignalDef("SKU", "sku", threshold_literal="Premium", comparator="contains"),
            SignalDef("Pull count", "pull_count", threshold_key="acr_pull_count_low", comparator="lt"),
        ),
        summary="Container registry uses Premium SKU with low pull volume.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.50,
    ),
    "ACR_STANDARD_EXTENDED": _spec(
        "standard_idle",
        signals=(
            SignalDef("SKU", "sku", threshold_literal="Standard", comparator="contains"),
            SignalDef("Pull count", "pull_count", threshold_key="acr_pull_count_low", comparator="lt"),
            SignalDef("Storage used", "storage_used_gb", threshold_key="acr_storage_high_gb", comparator="lt"),
        ),
        summary="Standard registry with low pulls and storage below high threshold.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.35,
    ),
    "ACR_GEO_REPLICATION_EXTENDED": _spec(
        "geo_replication",
        signals=(SignalDef("Replication regions", "replication_count", threshold_literal="1", comparator="gt"),),
        summary="ACR geo-replication count is {replication_count}.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.35,
    ),
    "ACR_STORAGE_HIGH_EXTENDED": _spec(
        "high_storage",
        signals=(
            SignalDef("Storage used", "storage_used_gb", threshold_key="acr_storage_high_gb", comparator="gte"),
            SignalDef("Pull count", "pull_count", threshold_key="acr_pull_count_low", comparator="lt"),
        ),
        summary="Registry storage is high ({storage_used_gb} GB) with low activity.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.25,
    ),
    "ACR_RETENTION_DISABLED_EXTENDED": _spec(
        "retention_disabled",
        signals=(
            SignalDef("Retention policy", "retention_policy_enabled", threshold_literal="enabled", comparator="falsy"),
            SignalDef("Storage used", "storage_used_gb", threshold_key="acr_storage_high_gb", comparator="gte"),
        ),
        summary="Premium registry has high storage and retention policy disabled.",
        savings_method="governance",
    ),
    # ── Security / Cost ────────────────────────────────────────────────────
    "KEYVAULT_SOFT_DELETE_OFF": _spec(
        "soft_delete_disabled",
        signals=(
            SignalDef("Soft delete", "enableSoftDelete", threshold_literal="enabled", comparator="falsy"),
            SignalDef("Purge protection", "enablePurgeProtection", threshold_literal="enabled", comparator="falsy"),
        ),
        summary="Key Vault missing soft-delete or purge protection.",
        savings_method="governance",
    ),
    "KEYVAULT_PROTECTION_EXTENDED": _spec(
        "soft_delete_disabled",
        signals=(
            SignalDef("Soft delete", "enableSoftDelete", threshold_literal="enabled", comparator="falsy"),
            SignalDef("Purge protection", "enablePurgeProtection", threshold_literal="enabled", comparator="falsy"),
        ),
        summary="Key Vault protection settings need hardening.",
        savings_method="governance",
    ),
    "KEYVAULT_IDLE_EXTENDED": _spec(
        "idle_vault",
        signals=(SignalDef("API hits", "api_hits", threshold_key="kv_api_hits_idle", comparator="lt"),),
        summary="Key Vault shows very low API activity.",
        savings_method="full_monthly_cost",
    ),
    "KEYVAULT_PREMIUM_EXTENDED": _spec(
        "premium_idle",
        signals=(
            SignalDef("SKU", "sku", threshold_literal="Premium", comparator="contains"),
            SignalDef("API hits", "api_hits", threshold_key="kv_api_hits_idle", comparator="lt"),
        ),
        summary="Premium Key Vault with low API activity.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.30,
    ),
    "KEYVAULT_HIGH_OPS_EXTENDED": _spec(
        "high_api_volume",
        signals=(SignalDef("API hits", "api_hits", threshold_key="kv_api_hits_high", comparator="gte"),),
        summary="Key Vault API volume is high ({api_hits} hits).",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.25,
    ),
    "BUDGET_WARNING": _spec(
        "budget_warning",
        signals=(SignalDef("Budget utilization", "used_pct", threshold_key="budget_warn_pct", comparator="gte", format_value=_fmt_pct),),
        summary="Budget is at {used_pct:.1f}% of limit.",
        savings_method="budget_guardrail",
    ),
    "BUDGET_CRITICAL": _spec(
        "budget_critical",
        signals=(SignalDef("Budget utilization", "used_pct", threshold_key="budget_crit_pct", comparator="gte", format_value=_fmt_pct),),
        summary="Budget is at {used_pct:.1f}% of limit (critical).",
        savings_method="budget_guardrail",
    ),
    "BUDGET_GUARDRAIL_EXTENDED": _spec(
        "budget_guardrail",
        signals=(SignalDef("Budget utilization", "used_pct", threshold_literal="80%", comparator="gte", format_value=_fmt_pct),),
        summary="Subscription budget guardrail triggered at {used_pct:.1f}%.",
        savings_method="budget_guardrail",
    ),
    "RESERVED_OPPORTUNITY": _spec(
        "reserved_opportunity",
        signals=(SignalDef("On-demand spend", "monthly_cost_usd", comparator="not_empty", format_value=_fmt_money),),
        summary="Workload may benefit from reserved capacity.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.40,
    ),
    "SAVINGS_PLAN_OPPORTUNITY": _spec(
        "savings_plan_opportunity",
        signals=(SignalDef("Compute spend", "monthly_cost_usd", comparator="not_empty", format_value=_fmt_money),),
        summary="Compute spend qualifies for Azure savings plan review.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.30,
    ),
    # ── Standard rules (no extended twin) ───────────────────────────────────
    "SQL_ELASTIC_POOL_CANDIDATE": _spec(
        "elastic_pool_candidate",
        signals=(
            SignalDef("Database count", "database_count", threshold_literal="> 1", comparator="gt"),
            SignalDef("Compute tier", "tier", comparator="not_empty"),
        ),
        summary="Multiple databases on one SQL server may consolidate into an elastic pool.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.20,
    ),
    "SQL_HYBRID_BENEFIT_CANDIDATE": _spec(
        "hybrid_benefit_candidate",
        signals=(
            SignalDef("Compute tier", "tier", threshold_literal="Provisioned", comparator="contains"),
            SignalDef("License type", "license_type", threshold_literal="LicenseIncluded", comparator="contains", optional=True),
        ),
        summary="Provisioned SQL may qualify for Azure Hybrid Benefit licensing.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.30,
    ),
    "SQL_QUERY_PERF_REVIEW": _spec(
        "query_performance_review",
        signals=(
            SignalDef("DTU/CPU utilization", "dtu_pct", threshold_key="cpu_upsize_pct", comparator="gte", format_value=_fmt_pct, optional=True),
            SignalDef("Compute tier", "tier", comparator="not_empty"),
        ),
        summary="SQL database may benefit from query tuning, indexing, or tier review.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.15,
    ),
    "NETWORK_DDOS_PLAN_REVIEW": _spec(
        "ddos_plan_review",
        signals=(
            SignalDef("DDoS protection", "ddos_protection", threshold_literal="Standard", comparator="contains"),
            SignalDef("IP allocation", "allocation", comparator="not_empty", optional=True),
        ),
        summary="Public IP uses DDoS Standard — confirm the protection tier is required.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.25,
    ),
    "NETWORK_TRAFFIC_MANAGER_IDLE": _spec(
        "traffic_manager_review",
        signals=(
            SignalDef("Profile status", "state", comparator="not_empty"),
            SignalDef("Endpoint count", "endpoint_count", threshold_literal="0", comparator="eq", optional=True),
        ),
        summary="Traffic Manager profile is active — validate routing endpoints and usage.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.20,
    ),
    "NETWORK_FRONT_DOOR_REVIEW": _spec(
        "front_door_review",
        signals=(
            SignalDef("Provisioning state", "provisioning_state", comparator="not_empty"),
            SignalDef("SKU", "sku", comparator="not_empty", optional=True),
        ),
        summary="Azure Front Door profile — review routing, WAF tier, and endpoint usage.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.20,
    ),
    "NETWORK_EXPRESSROUTE_REVIEW": _spec(
        "expressroute_review",
        signals=(
            SignalDef("Provisioning state", "provisioning_state", comparator="not_empty"),
            SignalDef("SKU", "sku", comparator="not_empty", optional=True),
        ),
        summary="ExpressRoute circuit — review bandwidth tier and peering utilization.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.20,
    ),
    "GOVERNANCE_TAG_ENFORCEMENT": _spec(
        "missing_governance_tags",
        signals=(SignalDef("Missing tags", "missing_tags", comparator="not_empty"),),
        summary="Resource is missing mandatory governance tags: {missing_tags}.",
        savings_method="governance",
    ),
    "FUNCTIONS_PLAN_OPTIMIZATION": _spec(
        "functions_plan_optimization",
        signals=(
            SignalDef("Hosting plan", "plan_sku", comparator="not_empty"),
            SignalDef("Always On", "alwaysOn", threshold_literal="enabled", comparator="truthy", optional=True),
        ),
        summary="Function app on a dedicated plan — consider Consumption or Flex Consumption.",
        savings_method="factor_of_monthly_cost",
        savings_factor=0.50,
    ),
}


_AKS_EVIDENCE_ALIASES: tuple[tuple[str, str], ...] = (
    ("AKS_NO_AUTOSCALER_EXTENDED", "AKS_NO_AUTOSCALER"),
    ("AKS_OLD_VERSION_EXTENDED", "AKS_OLD_VERSION"),
)
for _alias_id, _base_id in _AKS_EVIDENCE_ALIASES:
    if _base_id in RULE_EVIDENCE_SPECS and _alias_id not in RULE_EVIDENCE_SPECS:
        RULE_EVIDENCE_SPECS[_alias_id] = RULE_EVIDENCE_SPECS[_base_id]


def cost_export_evidence_spec(
    rule_id: str,
    *,
    min_monthly_cost: float,
    savings_factor: float,
    component: str,
) -> RuleEvidenceSpec:
    threshold_cost = f"≥ {_fmt_money(min_monthly_cost)}"
    return _spec(
        "cost_threshold_exceeded",
        signals=(
            SignalDef(
                "Month-to-date cost",
                "monthly_cost",
                threshold_key="min_monthly_cost",
                threshold_literal=threshold_cost,
                comparator="gte",
                format_value=_fmt_money,
            ),
            SignalDef(
                "ARM resource type",
                "arm_resource_type",
                comparator="not_empty",
            ),
            SignalDef(
                "Azure service",
                "azure_service_name",
                comparator="not_empty",
            ),
            SignalDef(
                "Resource group",
                "resource_group",
                comparator="not_empty",
                optional=True,
            ),
            SignalDef(
                "Location",
                "location",
                comparator="not_empty",
                optional=True,
            ),
            SignalDef(
                "Provisioning / sync state",
                "state",
                comparator="not_empty",
                optional=True,
            ),
            SignalDef(
                "SKU",
                "sku",
                comparator="not_empty",
                optional=True,
            ),
        ),
        summary="{summary}",
        savings_method="factor_of_monthly_cost",
        savings_factor=savings_factor,
        savings_desc=(
            f"Estimated savings = MTD cost × {savings_factor:.0%} "
            f"(rule threshold {threshold_cost}/mo for {component})."
        ),
        data_source="cost_export",
    )


def register_cost_export_specs(rules: list[Any]) -> None:
    for rule in rules:
        RULE_EVIDENCE_SPECS.setdefault(
            rule.id,
            cost_export_evidence_spec(
                rule.id,
                min_monthly_cost=rule.min_monthly_cost,
                savings_factor=rule.savings_factor,
                component=rule.component,
            ),
        )


def all_manifest_rule_ids() -> set[str]:
    return set(RULE_MANIFEST.keys())


def missing_specs() -> list[str]:
    return sorted(rid for rid in all_manifest_rule_ids() if rid not in RULE_EVIDENCE_SPECS)


_COMPARATOR_EXPECTED: dict[str, str] = {
    "not_empty": "Present",
    "empty": "None",
    "truthy": "Yes",
    "falsy": "No",
}

_THRESHOLD_KEY_FALLBACK: dict[str, str] = {
    "cpu_threshold_pct": "≤ idle CPU threshold",
    "cpu_oversize_threshold_pct": "≤ oversize CPU threshold",
    "cpu_idle_pct": "≤ idle CPU threshold",
    "mem_idle_pct": "≤ idle memory threshold",
    "memory_idle_pct": "≤ idle memory threshold",
    "min_monthly_savings_usd": "≥ minimum monthly savings",
    "vm_uptime_hours_candidate": "≥ uptime candidate threshold",
    "snapshot_retention_days": "≥ retention threshold",
    "snapshot_min_size_gb": "≥ minimum size gate",
    "acr_pull_count_low": "< low pull threshold",
    "acr_storage_high_gb": "≥ high storage threshold",
    "acr_push_count_low": "< low push threshold",
    "kv_api_hits_idle": "< idle API hits threshold",
    "kv_api_hits_high": "≥ high API hits threshold",
    "asp_min_apps_for_premium": "< premium app threshold",
    "redis_premium_min_capacity": "≥ premium capacity threshold",
    "db_dtu_idle_pct": "≤ idle DTU threshold",
    "sql_serverless_candidate_cpu_pct": "≤ serverless CPU threshold",
    "cosmos_autoscale_candidate_utilization_pct": "≤ autoscale utilization threshold",
    "budget_warn_pct": "≥ warning threshold",
    "budget_crit_pct": "≥ critical threshold",
    "aks_max_idle_node_ratio": "≥ idle node ratio threshold",
    "aks_min_system_nodes": "≥ minimum system nodes",
    "node_count_min": "> minimum node count",
    "disk_io_idle_bps": "< idle I/O threshold (B/s)",
    "disk_idle_min_size_gb": "≥ minimum size for idle I/O check",
    "disk_iops_block_downgrade_pct": "< block downgrade above IOPS utilization",
    "disk_iops_high_util_pct": "≥ under-provisioned IOPS utilization",
    "max_unattached_disk_days": "≥ max unattached disk age",
    "private_dns_max_default_record_sets": "> max default record sets",
    "storage_transaction_low": "< low monthly transaction threshold",
    "storage_egress_bytes_monthly": "≥ monthly egress threshold",
    "storage_utilization_low_pct": "< low utilization threshold",
}


_COMPARATOR_THRESHOLD_PREFIX: dict[str, str] = {
    "gt": ">",
    "gte": "≥",
    "lt": "<",
    "lte": "≤",
}


def _not_empty_expected(value_key: str, facts: dict[str, Any]) -> str:
    if value_key == "suggested_sku":
        current = facts.get("vm_size") or facts.get("current_sku")
        if current:
            return f"≠ {current}"
        return "Recommended alternative SKU"
    if value_key == "sizing_action":
        return "downgrade, cross_family, or upgrade"
    if value_key == "suggested_family":
        current = facts.get("sku_family") or facts.get("current_family")
        if current:
            return f"≠ {current}"
        return "Recommended alternative family"
    if value_key in {"environment", "environment_tag"}:
        return "Required tag present"
    if value_key in {"tier", "sku", "sku_tier"}:
        return "Configured in inventory"
    if value_key == "kubernetes_version":
        return "Supported version on record"
    if value_key == "node_count":
        return "> 0 nodes"
    if value_key == "capacity":
        return "> 0 capacity units"
    if value_key == "size_gb":
        return "> 0 GB"
    if value_key == "storage_gb":
        return "> 0 GB allocated"
    if value_key == "monthly_cost_usd":
        return "> $0 spend"
    if value_key == "resource_group":
        return "Present"
    if value_key == "location":
        return "Present in inventory"
    if value_key == "state":
        return "Present in inventory"
    if value_key == "arm_resource_type":
        return "Present"
    if value_key == "azure_service_name":
        return "Present"
    return _COMPARATOR_EXPECTED["not_empty"]


def _resolve_threshold(signal: SignalDef, facts: dict[str, Any]) -> str:
    if signal.threshold_literal:
        return signal.threshold_literal
    if signal.threshold_key:
        if signal.threshold_key in facts:
            val = facts[signal.threshold_key]
            if signal.format_value:
                formatted = signal.format_value(val)
            else:
                formatted = str(val)
            prefix = _COMPARATOR_THRESHOLD_PREFIX.get(signal.comparator or "")
            if prefix and formatted not in ("", "—"):
                return f"{prefix} {formatted}"
            return formatted
        fallback = _THRESHOLD_KEY_FALLBACK.get(signal.threshold_key)
        if fallback:
            return fallback
    if signal.comparator == "not_empty":
        return _not_empty_expected(signal.value_key, facts)
    if signal.comparator in _COMPARATOR_EXPECTED:
        return _COMPARATOR_EXPECTED[signal.comparator]
    return "—"


def _resolve_value(signal: SignalDef, facts: dict[str, Any]) -> Any:
    val = facts.get(signal.value_key)
    if signal.format_value and val is not None:
        return signal.format_value(val)
    return val


def _compare(comparator: str, observed: Any, facts: dict[str, Any], signal: SignalDef) -> bool:
    if observed is None and comparator not in ("falsy", "truthy", "empty", "not_empty"):
        return False

    threshold_raw = facts.get(signal.threshold_key) if signal.threshold_key else None

    if comparator == "truthy":
        return bool(observed)
    if comparator == "falsy":
        return not bool(observed)
    if comparator == "not_empty":
        if isinstance(observed, (list, dict, str)):
            return len(observed) > 0
        return observed is not None and observed != ""
    if comparator == "empty":
        if isinstance(observed, (list, dict, str)):
            return len(observed) == 0
        return not observed
    if comparator == "eq":
        target = threshold_raw if threshold_raw is not None else signal.threshold_literal
        return str(observed).lower() == str(target).lower()
    if comparator == "neq":
        target = threshold_raw if threshold_raw is not None else signal.threshold_literal
        return str(observed).lower() != str(target).lower()
    if comparator == "contains":
        target = str(threshold_raw or signal.threshold_literal or "")
        return target.lower() in str(observed or "").lower()
    if comparator == "lt":
        try:
            return float(observed) < float(threshold_raw or 1)
        except (TypeError, ValueError):
            return False
    if comparator == "gt":
        try:
            return float(observed) > float(threshold_raw or 0)
        except (TypeError, ValueError):
            return False
    if comparator == "lte":
        try:
            limit = float(threshold_raw) if threshold_raw is not None else float(str(signal.threshold_literal or "0").replace("≤", "").replace("%", "").strip())
            return float(observed) <= limit
        except (TypeError, ValueError):
            return False
    if comparator == "gte":
        try:
            limit = float(threshold_raw) if threshold_raw is not None else float(str(signal.threshold_literal or "0").replace("≥", "").replace("%", "").replace("$", "").strip())
            return float(observed) >= limit
        except (TypeError, ValueError):
            return False
    return bool(observed)


# Cost/billing signals are shown once in optimization_metrics.cost — not duplicated in checks.
_COST_CHECK_VALUE_KEYS = frozenset({
    "monthly_cost",
    "monthly_cost_usd",
    "min_monthly_cost",
    "current_spend_usd",
    "forecast_spend_usd",
    "amount",
    "azure_service_name",
})


def build_checks(
    spec: RuleEvidenceSpec,
    facts: dict[str, Any],
    *,
    resource_type: str = "",
    rule_id: str = "",
) -> list[dict[str, Any]]:
    """Build decision signals — cost and utilization metrics live in optimization_metrics only."""
    from app.service_display import (
        format_service_fact,
        format_threshold_display,
        inventory_missing_display,
        missing_display,
        resolve_canonical_type,
    )

    canonical = resolve_canonical_type(
        resource_type or str(facts.get("resource_type") or ""),
        rule_id,
    )
    checks: list[dict[str, Any]] = []
    for sig in spec.signals:
        if sig.value_key in _COST_CHECK_VALUE_KEYS:
            continue
        raw = facts.get(sig.value_key)
        threshold = _resolve_threshold(sig, facts)

        if sig.optional and (raw is None or raw == ""):
            checks.append({
                "signal": sig.signal,
                "value": inventory_missing_display(),
                "threshold": "Not required when absent",
                "value_display": inventory_missing_display(),
                "threshold_display": "Not required when absent",
                "passed": True,
                "status": "na",
                "fact_key": sig.value_key,
            })
            continue

        if raw is None or raw == "":
            value_display = missing_display(canonical)
        elif sig.format_value:
            value_display = sig.format_value(raw)
        else:
            value_display = format_service_fact(canonical, sig.value_key, raw)

        threshold_display = threshold
        if sig.threshold_key and facts.get(sig.threshold_key) is not None and not sig.threshold_literal:
            threshold_display = format_threshold_display(
                canonical,
                sig.threshold_key,
                facts.get(sig.threshold_key),
                comparator=sig.comparator or "",
            )
        elif sig.threshold_key and sig.threshold_key in facts and sig.format_value:
            threshold_display = threshold

        passed = _compare(sig.comparator, raw, facts, sig)
        checks.append({
            "signal": sig.signal,
            "value": value_display,
            "threshold": threshold_display,
            "value_display": value_display,
            "threshold_display": threshold_display,
            "passed": passed,
            "status": "pass" if passed else "fail",
            "fact_key": sig.value_key,
        })
    return checks


def format_summary(template: str, facts: dict[str, Any], fallback: str = "") -> str:
    if not template:
        return fallback
    try:
        return template.format_map(_SafeFormatDict(facts))
    except (KeyError, ValueError, TypeError):
        return fallback or template


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "—"


# Keys that belong to savings/cost export — excluded from resource technical details.
_RESOURCE_DETAIL_SKIP = frozenset({
    "summary",
    "checks",
    "determination",
    "data_source",
    "source",
    "savings_methodology",
    "monthly_cost",
    "monthly_cost_usd",
    "min_monthly_cost",
    "savings_factor",
    "cost_export_only",
    "in_inventory",
    "passed",
    "status",
    "resource_details",
    "sku_label",
    "service_name",
    "azure_service_name",
    "billing_service_name",
    "billingServiceName",
    "properties",
    "tags",
    "optimization_metrics",
    "estimated_savings_usd",
    "annualized_savings_usd",
    "confidence_score",
    "waste_score",
    # Assessment contracts + structured evidence (not inventory rows)
    "required_evidence",
    "evidence_rows",
    "evidence_factors",
    "exclude_inventory_facts",
    "_evidence_meta",
    "assessment_file",
    "rule_thresholds",
    "data_quality",
    "creation_data",
    "creationData",
    # Disk engine threshold overrides
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
    "disk_read_bps",
    "disk_write_bps",
    "disk_read_iops",
    "disk_write_iops",
    "disk_iops_utilization_pct",
    "disk_throughput_utilization_pct",
    "disk_combined_iops",
    "provisioned_iops",
    "provisioned_mbps",
})

# Utilization metrics live in optimization_metrics.performance — not resource_details.
_UTILIZATION_DETAIL_SKIP = frozenset({
    "avg_cpu_pct",
    "avg_memory_pct",
    "memory_usage_pct",
    "avg_available_memory_bytes",
})

# Configuration-style performance facts (SKU, listeners) — keep for cost export + inventory.
_CONFIG_PERF_DETAIL_SKIP = frozenset(
    key for key in PERFORMANCE_FACT_KEYS if key not in _UTILIZATION_DETAIL_SKIP
)

from app.rule_evidence_config import INVENTORY_PROPERTY_FACT_KEYS as _INVENTORY_PROPERTY_KEYS  # noqa: E402

_INVENTORY_DETAIL_SKIP = _CONFIG_PERF_DETAIL_SKIP | _INVENTORY_PROPERTY_KEYS


def _skip_resource_detail_key(key: str, facts: dict[str, Any]) -> bool:
    if key in _RESOURCE_DETAIL_SKIP:
        return True
    if key in _UTILIZATION_DETAIL_SKIP:
        return True
    if key in _CONFIG_PERF_DETAIL_SKIP:
        if facts.get("data_source") == "cost_export" and facts.get("in_inventory"):
            return False
        return True
    if key in _INVENTORY_DETAIL_SKIP:
        return True
    return False

_COST_EXPORT_DETAIL_SKIP = frozenset({
    "azure_service_name",
    "billing_service_name",
    "billingServiceName",
    "resource_type",
    "canonical_resource_type",
    "cost_export_only",
    "in_inventory",
    "min_monthly_cost",
})


_DATETIME_DETAIL_KEYS = frozenset({
    "last_ownership_update",
    "last_ownership_update_time",
    "time_created",
})


def _detail_display(key: str, val: Any) -> Any:
    display = _scalar_or_display(val)
    if display is None or display == "":
        return None
    if key in _DATETIME_DETAIL_KEYS:
        from app.optimization_metrics import _fmt_datetime
        formatted = _fmt_datetime(display)
        return formatted if formatted != "Not available" else display
    return display


def _merge_disk_lineage_facts(out: dict[str, Any], finding: dict[str, Any]) -> dict[str, Any]:
    rt = (finding.get("resource_type") or out.get("resource_type") or "").lower()
    arm = (out.get("arm_resource_type") or "").lower()
    if rt != "compute/disk" and "microsoft.compute/disks" not in arm:
        return out
    from app.disk_staleness import disk_lineage_from_facts
    lineage = disk_lineage_from_facts(out)
    if not lineage:
        return out
    merged = dict(out)
    for key, val in lineage.items():
        if val is not None and merged.get(key) in (None, ""):
            merged[key] = val
    return merged


def _camel_to_snake(name: str) -> str:
    if not name:
        return name
    out: list[str] = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and (name[i - 1].islower() or (i + 1 < len(name) and name[i + 1].islower())):
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def _scalar_or_display(val: Any) -> Any:
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float, str)):
        return val
    if isinstance(val, dict):
        for key in ("name", "code", "tier", "value", "id"):
            if val.get(key) not in (None, ""):
                return val[key]
        if len(val) <= 4:
            return ", ".join(f"{k}: {_scalar_or_display(v)}" for k, v in val.items() if v is not None)
        return None
    if isinstance(val, list):
        if not val:
            return None
        if all(not isinstance(x, (dict, list)) for x in val):
            return val
        return len(val)
    return str(val)


def build_resource_details(facts: dict[str, Any]) -> dict[str, Any]:
    """Inventory and configuration fields used to justify the finding (not cost export rows)."""
    is_cost_export = (facts or {}).get("data_source") == "cost_export"
    existing = facts.get("resource_details")
    if isinstance(existing, dict) and existing:
        return {
            k: v for k, v in existing.items()
            if v is not None and v != "" and not _skip_resource_detail_key(k, facts)
            and (not is_cost_export or k not in _COST_EXPORT_DETAIL_SKIP)
        }

    details: dict[str, Any] = {}
    for key, val in (facts or {}).items():
        if _skip_resource_detail_key(key, facts):
            continue
        if is_cost_export and key in _COST_EXPORT_DETAIL_SKIP:
            continue
        display = _detail_display(key, val)
        if display is not None and display != "":
            details[key] = display

    props = facts.get("properties")
    if isinstance(props, dict):
        if props.get("source") == "cost_export" and len(props) <= 2:
            props = {}
        for pk, pv in props.items():
            norm = _camel_to_snake(pk)
            if norm in details or _skip_resource_detail_key(norm, facts):
                continue
            if is_cost_export and norm in _COST_EXPORT_DETAIL_SKIP:
                continue
            display = _detail_display(norm, pv)
            if display is not None and display != "":
                details.setdefault(norm, display)

    return details


def _arm_provider_from_id(resource_id: str) -> str:
    rid = (resource_id or "").strip().lower()
    if "/providers/" not in rid:
        return ""
    parts = rid.split("/")
    try:
        idx = parts.index("providers")
        return f"{parts[idx + 1]}/{parts[idx + 2]}"
    except (ValueError, IndexError):
        return ""


def _merge_cost_export_facts(facts: dict[str, Any], finding: dict[str, Any]) -> dict[str, Any]:
    """Ensure cost-export evidence has identity fields derived from cost + inventory."""
    from app.inventory_technical import arm_resource_type_for_finding

    out = dict(facts or {})
    rid = (
        finding.get("resource_id")
        or out.get("resource_id")
        or ""
    )
    if rid:
        arm = arm_resource_type_for_finding(
            rid,
            out.get("arm_resource_type") or finding.get("resource_type") or "",
        )
        if arm:
            out["arm_resource_type"] = arm
    if not out.get("resource_group"):
        rg = finding.get("resource_group") or out.get("resource_group")
        if not rg and rid:
            parts = rid.split("/")
            try:
                idx = parts.index("resourcegroups")
                rg = parts[idx + 1]
            except (ValueError, IndexError):
                rg = ""
        if rg:
            out["resource_group"] = rg
    if not out.get("location") and finding.get("location"):
        out["location"] = finding["location"]
    if not out.get("state") and finding.get("state"):
        out["state"] = finding["state"]
    service = (
        out.get("azure_service_name")
        or out.get("billingServiceName")
        or out.get("billing_service_name")
        or out.get("service_name")
        or finding.get("azure_service_name")
        or ""
    )
    if service:
        out["azure_service_name"] = service
    monthly = out.get("monthly_cost") or out.get("monthly_cost_usd")
    if monthly is not None:
        out.setdefault("monthly_cost", monthly)
        out.setdefault("monthly_cost_usd", monthly)
    details = out.get("resource_details")
    if isinstance(details, dict):
        for key, val in details.items():
            if key not in out and val not in (None, ""):
                out[key] = val
    return out


def attach_savings_methodology(
    evidence: dict[str, Any],
    spec: RuleEvidenceSpec | None,
    *,
    estimated_savings_usd: float | None,
    facts: dict[str, Any],
) -> dict[str, Any]:
    out = dict(evidence)
    monthly = out.get("monthly_cost_usd") or out.get("monthly_cost")
    savings_def = spec.savings if spec else SavingsDef(method="unknown")

    factor = savings_def.factor
    if factor is None and savings_def.factor_key:
        factor = facts.get(savings_def.factor_key)

    methodology = {
        "method": savings_def.method,
        "description": savings_def.description,
        "estimated_monthly_savings_usd": estimated_savings_usd,
        "baseline_monthly_cost_usd": monthly,
    }
    if factor is not None:
        methodology["savings_factor"] = factor
        if monthly and savings_def.method == "factor_of_monthly_cost":
            methodology["formula"] = f"${float(monthly):,.2f} × {float(factor):.0%} = ${estimated_savings_usd or 0:,.2f}"
    elif savings_def.method == "azure_retail_sku_diff":
        current = facts.get("current_sku_monthly_usd") or facts.get("current_tier_monthly_usd")
        suggested = facts.get("suggested_sku_monthly_usd") or facts.get("suggested_tier_monthly_usd")
        retail_savings = facts.get("retail_monthly_savings_usd")
        run_rate = facts.get("monthly_run_rate_usd")
        basis = facts.get("savings_basis")
        if (
            basis == "monthly_run_rate"
            and run_rate
            and current is not None
            and suggested is not None
            and float(current) > 0
        ):
            ratio = float(suggested) / float(current)
            methodology["formula"] = (
                f"Monthly run-rate ${float(run_rate):,.2f}/mo × (1 − ${float(suggested):,.2f} ÷ ${float(current):,.2f}) "
                f"= ${estimated_savings_usd or facts.get('run_rate_monthly_savings_usd') or 0:,.2f}/mo"
            )
            if retail_savings is not None:
                methodology["retail_formula"] = (
                    f"Retail list-price ceiling: ${float(current):,.2f}/mo − ${float(suggested):,.2f}/mo "
                    f"= ${float(retail_savings):,.2f}/mo"
                )
            mtd = facts.get("mtd_cost_usd")
            if mtd:
                methodology["mtd_cost_usd"] = mtd
        elif current is not None and suggested is not None:
            methodology["formula"] = (
                f"Azure retail ${float(current):,.2f}/mo − ${float(suggested):,.2f}/mo "
                f"= ${float(retail_savings if retail_savings is not None else estimated_savings_usd or 0):,.2f}/mo"
            )
        methodology["pricing_source"] = facts.get("pricing_source", "azure_retail_prices")
        methodology["savings_basis"] = basis
        if facts.get("hours_per_month"):
            methodology["hours_per_month"] = facts.get("hours_per_month")
    elif savings_def.method == "full_monthly_cost" and monthly:
        methodology["formula"] = f"Full MTD cost ${float(monthly):,.2f}"

    out["savings_methodology"] = methodology
    return out


def apply_rule_evidence_spec(
    rule_id: str,
    facts: dict[str, Any],
    *,
    finding: dict[str, Any] | None = None,
    estimated_savings_usd: float | None = None,
) -> dict[str, Any]:
    """Build structured evidence from rule spec + runtime facts."""
    finding = finding or {}
    rid = (rule_id or "").upper()
    spec = resolve_rule_evidence_spec(rid, facts) or RULE_EVIDENCE_SPECS.get(rid)
    out = dict(facts or {})
    is_cost_export = (
        out.get("data_source") == "cost_export"
        or out.get("source") == "cost_export"
        or (spec and spec.data_source == "cost_export")
    )
    if is_cost_export:
        out = _merge_cost_export_facts(out, finding)

    if spec:
        requested_determination = str((facts or {}).get("determination") or "").strip().lower()
        default_spec = RULE_EVIDENCE_SPECS.get(rid)
        variant_active = (
            requested_determination
            and default_spec is not None
            and requested_determination != default_spec.determination
        )
        out["determination"] = spec.determination
        if not is_cost_export:
            out["data_source"] = spec.data_source
        rebuild_checks = is_cost_export or not out.get("checks") or variant_active
        if rebuild_checks:
            built = build_checks(
                spec,
                out,
                resource_type=str(finding.get("resource_type") or ""),
                rule_id=rid,
            )
            if built:
                out["checks"] = built
        if spec.summary_template and (not out.get("summary") or variant_active):
            out["summary"] = format_summary(
                spec.summary_template,
                out,
                fallback=finding.get("detail") or "",
            )
        out = attach_savings_methodology(out, spec, estimated_savings_usd=estimated_savings_usd, facts=out)
        out = _merge_disk_lineage_facts(out, finding)
        out["resource_details"] = build_resource_details(out)
        from app.rule_evidence_config import required_evidence_for_rule

        req = required_evidence_for_rule(
            rid,
            str(finding.get("resource_type") or out.get("resource_type") or ""),
        )
        if req:
            out["required_evidence"] = req
        if facts.get("evidence_rows"):
            out["evidence_rows"] = list(facts["evidence_rows"])
        if facts.get("evidence_factors"):
            out["evidence_factors"] = list(facts["evidence_factors"])
        if facts.get("exclude_inventory_facts"):
            out["exclude_inventory_facts"] = True
        if facts.get("_evidence_meta"):
            out["_evidence_meta"] = dict(facts["_evidence_meta"])
        return attach_optimization_metrics(
            out,
            finding=finding,
            rule_id=rid,
            resource_type=finding.get("resource_type", ""),
        )

    # Generic fallback for rules without a dedicated spec yet
    out.setdefault("determination", "rule_triggered")
    out.setdefault("data_source", finding.get("data_source") or "synced_inventory")
    if not out.get("summary"):
        out["summary"] = finding.get("detail") or ""
    out = attach_savings_methodology(out, None, estimated_savings_usd=estimated_savings_usd, facts=out)
    out = _merge_disk_lineage_facts(out, finding)
    out["resource_details"] = build_resource_details(out)
    return attach_optimization_metrics(
        out,
        finding=finding,
        rule_id=rid,
        resource_type=finding.get("resource_type", ""),
    )


from app.cost_export_recommendations import COST_EXPORT_RULES  # noqa: E402
from app.optimizer.advanced_rules import ADVANCED_RULES  # noqa: E402


def register_extended_specs(rules: dict[str, Any]) -> None:
    """Auto-register evidence specs for extended rules without dedicated specs."""
    for rid, rule in rules.items():
        if rid in RULE_EVIDENCE_SPECS:
            continue
        method = "factor_of_monthly_cost" if rule.category.value == "COST" else "governance"
        RULE_EVIDENCE_SPECS.setdefault(
            rid,
            _spec(
                rid.lower(),
                summary=rule.description,
                savings_method=method,
                savings_factor=0.25 if method == "factor_of_monthly_cost" else None,
                data_source="synced_inventory",
            ),
        )


register_cost_export_specs(COST_EXPORT_RULES)
register_extended_specs(ADVANCED_RULES)


def register_alias_evidence_specs() -> None:
    """Mirror evidence specs for UI/resource-module rule aliases."""
    from app.optimizer.rule_catalog import RULE_ALIASES

    for alias, canonical in RULE_ALIASES.items():
        if canonical in RULE_EVIDENCE_SPECS and alias not in RULE_EVIDENCE_SPECS:
            RULE_EVIDENCE_SPECS[alias] = RULE_EVIDENCE_SPECS[canonical]


register_alias_evidence_specs()
