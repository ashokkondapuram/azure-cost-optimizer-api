"""Central registry for per-resource technical fetch and monitor profiles."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.azure_monitor_aggregations import azure_metrics_doc_url
from app.focus_mapping import normalize_arm_id
from app.resource_type_map import arm_provider_type
from app.resources.analytics import adx, databricks, mlworkspace, synapse
from app.resources.appservice import plan, webapp
from app.resources.backup import recoveryvault
from app.resources.compute import disk, snapshot, vm, vmss
from app.resources.containers import acr, aks
from app.resources.database import cosmosdb, postgresql, redis, sql, sql_database
from app.resources.integration import apim, datafactory, logicapp
from app.resources.messaging import eventhub, servicebus
from app.resources.monitoring import appinsights, loganalytics
from app.resources.network import appgateway, cdn, expressroute, firewall, frontdoor, loadbalancer, nat, nic, nsg, privatedns, privateendpoint, privatelinkservice, publicip, trafficmanager, vnet
from app.resources.search import cognitivesearch
from app.resources.security import keyvault
from app.resources.storage import account
from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, UsageMetricDef

ALL_RESOURCE_MODULES: list[Any] = [
    vm,
    vmss,
    disk,
    snapshot,
    aks,
    acr,
    account,
    publicip,
    vnet,
    loadbalancer,
    appgateway,
    nic,
    nat,
    nsg,
    firewall,
    cdn,
    expressroute,
    trafficmanager,
    frontdoor,
    privateendpoint,
    privatelinkservice,
    privatedns,
    sql,
    sql_database,
    cosmosdb,
    postgresql,
    redis,
    webapp,
    plan,
    keyvault,
    loganalytics,
    appinsights,
    apim,
    datafactory,
    logicapp,
    eventhub,
    servicebus,
    databricks,
    synapse,
    adx,
    mlworkspace,
    recoveryvault,
    cognitivesearch,
]


def _build_resource_monitor_profiles() -> dict[str, ResourceMonitorProfile]:
    from app.azure_monitor_aggregations import enrich_monitor_profile

    profiles: dict[str, ResourceMonitorProfile] = {}
    for mod in ALL_RESOURCE_MODULES:
        profile = getattr(mod, "MONITOR_PROFILE", None)
        if profile is not None:
            profiles[profile.monitor_arm_type] = enrich_monitor_profile(profile)
        for extra in getattr(mod, "EXTRA_MONITOR_PROFILES", ()) or ():
            profiles[extra.monitor_arm_type] = enrich_monitor_profile(extra)
    return profiles


def assessment_driven_fetch_spec(canonical_type: str) -> TechnicalFetchSpec | None:
    """Return assessment-backed fetch spec when available."""
    key = (canonical_type or "").strip().lower()
    if key in {"compute/disk", "database/cosmosdb"}:
        return get_technical_fetch_spec(key)
    return None


def assessment_driven_monitor_profile(canonical_type: str) -> ResourceMonitorProfile | None:
    """Return assessment-backed monitor profile when available."""
    key = (canonical_type or "").strip().lower()
    from app.azure_monitor_aggregations import enrich_monitor_profile

    if key == "compute/disk":
        from it_services.compute_disk.assessment_bridge import build_disk_monitor_profile

        return enrich_monitor_profile(build_disk_monitor_profile())
    if key == "database/cosmosdb":
        from it_services.database_cosmosdb.assessment_bridge import build_cosmos_monitor_profile

        return enrich_monitor_profile(build_cosmos_monitor_profile())
    return None


RESOURCE_MONITOR_PROFILES: dict[str, ResourceMonitorProfile] = _build_resource_monitor_profiles()


def to_usage_metric_defs(profile: ResourceMonitorProfile) -> tuple[UsageMetricDef, ...]:
    return tuple(
        UsageMetricDef(
            source="azure_monitor",
            metric_name=m.metric_name,
            fact_key=m.fact_key,
            description=m.description,
            timespan=m.timespan,
            rules=m.rules,
            aggregation=m.aggregation,
        )
        for m in profile.metrics
    )


def profiles_for_canonical(canonical_type: str) -> tuple[ResourceMonitorProfile, ...]:
    key = (canonical_type or "").strip().lower()
    return tuple(p for p in RESOURCE_MONITOR_PROFILES.values() if p.canonical_type == key)


def usage_metrics_for_canonical(canonical_type: str) -> tuple[UsageMetricDef, ...]:
    seen: set[tuple[str, str]] = set()
    out: list[UsageMetricDef] = []
    for profile in profiles_for_canonical(canonical_type):
        for metric_def in to_usage_metric_defs(profile):
            key = (metric_def.metric_name, metric_def.fact_key)
            if key in seen:
                continue
            seen.add(key)
            out.append(metric_def)
    return tuple(out)


def attach_utilization_metrics(specs: dict[str, TechnicalFetchSpec]) -> dict[str, TechnicalFetchSpec]:
    updated: dict[str, TechnicalFetchSpec] = {}
    for key, spec in specs.items():
        monitor_metrics = usage_metrics_for_canonical(spec.canonical_type)
        extra = tuple(
            getattr(mod, "EXTRA_USAGE_METRICS", ())
            for mod in ALL_RESOURCE_MODULES
            if getattr(mod, "CANONICAL_TYPE", None) == spec.canonical_type
        )
        extra_metrics = tuple(m for group in extra for m in group)
        preserved = tuple(m for m in spec.usage_metrics if m.source != "azure_monitor")
        merged = monitor_metrics + preserved + extra_metrics
        if merged:
            updated[key] = replace(spec, usage_metrics=merged)
        else:
            updated[key] = spec
    return updated


def _build_technical_fetch_specs() -> dict[str, TechnicalFetchSpec]:
    base: dict[str, TechnicalFetchSpec] = {}
    for mod in ALL_RESOURCE_MODULES:
        spec = getattr(mod, "TECHNICAL_FETCH_SPEC", None)
        if spec is not None:
            base[spec.canonical_type] = spec
    return attach_utilization_metrics(base)


TECHNICAL_FETCH_SPECS: dict[str, TechnicalFetchSpec] = _build_technical_fetch_specs()

_GENERIC_ARM_SYNC_TYPES: tuple[tuple[str, str], ...] = tuple(
    (spec.arm_type, spec.canonical_type)
    for spec in TECHNICAL_FETCH_SPECS.values()
    if spec.generic_arm_sync
)


def get_technical_fetch_spec(canonical_type: str) -> TechnicalFetchSpec | None:
    return TECHNICAL_FETCH_SPECS.get((canonical_type or "").strip().lower())


def get_technical_fetch_spec_by_arm(arm_type: str) -> TechnicalFetchSpec | None:
    key = (arm_type or "").strip().lower()
    for spec in TECHNICAL_FETCH_SPECS.values():
        if spec.arm_type.lower() == key:
            return spec
    return None


def monitor_arm_type(resource_id: str) -> str:
    rid = normalize_arm_id(resource_id).lower()
    if not rid:
        return ""
    if "/microsoft.sql/servers/" in rid and "/databases/" in rid:
        return "microsoft.sql/servers/databases"
    if "/virtualmachinescalesets/" in rid and "/virtualmachines/" in rid:
        return "microsoft.compute/virtualmachinescalesets/virtualmachines"
    return arm_provider_type(resource_id)


def get_monitor_profile(resource_id: str, canonical_type: str | None = None) -> ResourceMonitorProfile | None:
    arm_type = monitor_arm_type(resource_id)
    if arm_type in RESOURCE_MONITOR_PROFILES:
        return RESOURCE_MONITOR_PROFILES[arm_type]
    if canonical_type:
        for profile in RESOURCE_MONITOR_PROFILES.values():
            if profile.canonical_type == canonical_type and profile.monitor_arm_type == arm_type:
                return profile
    return None


def list_monitor_profiles() -> list[dict[str, Any]]:
    return [
        {
            "monitor_arm_type": p.monitor_arm_type,
            "canonical_type": p.canonical_type,
            "display_name": p.display_name,
            "doc_ref": p.doc_ref,
            "doc_url": azure_metrics_doc_url(p.doc_ref) if p.doc_ref else None,
            "metrics": [
                {
                    "metric_name": m.metric_name,
                    "fact_key": m.fact_key,
                    "description": m.description,
                    "label": m.description,
                    "aggregation": m.aggregation,
                    "timespan": m.timespan,
                    "rules": list(m.rules),
                    "unit": m.unit,
                    "primary_stat": m.primary_stat,
                    "display_stats": list(m.display_stats),
                    "supported_aggregations": list(m.supported_aggregations),
                    "impact": m.impact,
                }
                for m in p.metrics
            ],
        }
        for p in sorted(RESOURCE_MONITOR_PROFILES.values(), key=lambda x: x.monitor_arm_type)
    ]


def generic_arm_sync_types() -> tuple[tuple[str, str], ...]:
    return _GENERIC_ARM_SYNC_TYPES
