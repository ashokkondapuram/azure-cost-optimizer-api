"""Azure Monitor supported aggregations per metric (from Microsoft Learn supported-metrics pages).

Source: https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-metrics/
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.resources.types import ResourceMonitorProfile, UtilizationMetric

# Azure REST aggregation name -> lowercase stat key in API payloads.
AZURE_AGG_TO_STAT_KEY: dict[str, str] = {
    "Average": "average",
    "Minimum": "minimum",
    "Maximum": "maximum",
    "Total": "total",
    "Count": "count",
}

STAT_KEY_TO_AZURE_AGG: dict[str, str] = {v: k for k, v in AZURE_AGG_TO_STAT_KEY.items()}

# (monitor_arm_type, metric_name) -> supported Azure aggregation types for that metric.
# Values are taken from the Aggregation column on each resource's supported-metrics page.
METRIC_SUPPORTED_AGGREGATIONS: dict[tuple[str, str], tuple[str, ...]] = {
    ("microsoft.compute/virtualmachines", "Percentage CPU"): ("Average",),
    ("microsoft.compute/virtualmachines", "Available Memory Bytes"): ("Average",),
    ("microsoft.compute/virtualmachinescalesets", "Percentage CPU"): ("Average",),
    ("microsoft.compute/virtualmachinescalesets", "Available Memory Bytes"): ("Average",),
    ("microsoft.compute/disks", "Composite Disk Read Bytes/sec"): ("Average",),
    ("microsoft.compute/disks", "Composite Disk Write Bytes/sec"): ("Average",),
    ("microsoft.compute/disks", "Composite Disk Read Operations/sec"): ("Average",),
    ("microsoft.compute/disks", "Composite Disk Write Operations/sec"): ("Average",),
    ("microsoft.storage/storageaccounts", "UsedCapacity"): ("Average",),
    ("microsoft.storage/storageaccounts", "Transactions"): ("Total",),
    ("microsoft.web/serverfarms", "CpuPercentage"): ("Average",),
    ("microsoft.web/serverfarms", "MemoryPercentage"): ("Average",),
    ("microsoft.web/sites", "CpuTime"): ("Count", "Total", "Minimum", "Maximum"),
    ("microsoft.web/sites", "AverageMemoryWorkingSet"): ("Average",),
    ("microsoft.web/sites", "Requests"): ("Total",),
    ("microsoft.cache/redis", "usedmemorypercentage"): ("Maximum",),
    ("microsoft.cache/redis", "cachehits"): ("Total",),
    ("microsoft.cache/redis", "operationsPerSecond"): ("Maximum",),
    ("microsoft.sql/servers/databases", "cpu_percent"): ("Average", "Maximum", "Minimum"),
    ("microsoft.sql/servers/databases", "storage_percent"): ("Average", "Maximum", "Minimum"),
    ("microsoft.dbforpostgresql/flexibleservers", "cpu_percent"): ("Average", "Maximum", "Minimum"),
    ("microsoft.dbforpostgresql/flexibleservers", "memory_percent"): ("Average", "Maximum", "Minimum"),
    ("microsoft.dbforpostgresql/flexibleservers", "storage_percent"): ("Average", "Maximum", "Minimum"),
    ("microsoft.documentdb/databaseaccounts", "TotalRequests"): ("Count",),
    ("microsoft.documentdb/databaseaccounts", "TotalRequestUnits"): ("Total", "Average", "Maximum"),
    ("microsoft.network/publicipaddresses", "ByteCount"): ("Total",),
    ("microsoft.network/publicipaddresses", "PacketCount"): ("Total",),
    ("microsoft.network/natgateways", "ByteCount"): ("Total",),
    ("microsoft.network/natgateways", "SNATConnectionCount"): ("Total",),
    ("microsoft.network/loadbalancers", "DipAvailability"): ("Average",),
    ("microsoft.network/loadbalancers", "ByteCount"): ("Total",),
    ("microsoft.network/applicationgateways", "HealthyHostCount"): ("Average",),
    ("microsoft.network/applicationgateways", "Throughput"): ("Average",),
    ("microsoft.network/applicationgateways", "TotalRequests"): ("Total",),
    ("microsoft.network/networkinterfaces", "BytesReceivedRate"): ("Total",),
    ("microsoft.network/networkinterfaces", "BytesSentRate"): ("Total",),
    ("microsoft.keyvault/vaults", "ServiceApiHit"): ("Count",),
    ("microsoft.keyvault/vaults", "ServiceApiResult"): ("Count",),
    ("microsoft.keyvault/vaults", "Availability"): ("Average",),
    ("microsoft.containerservice/managedclusters", "node_cpu_usage_percentage"): ("Maximum", "Average"),
    ("microsoft.containerservice/managedclusters", "node_memory_working_set_percentage"): ("Maximum", "Average"),
    ("microsoft.containerregistry/registries", "TotalPullCount"): ("Total",),
    ("microsoft.containerregistry/registries", "TotalPushCount"): ("Total",),
    ("microsoft.containerregistry/registries", "StorageUsed"): ("Average",),
    ("microsoft.servicebus/namespaces", "ActiveMessages"): ("Average", "Minimum", "Maximum"),
    ("microsoft.servicebus/namespaces", "IncomingRequests"): ("Total",),
    ("microsoft.eventhub/namespaces", "IncomingMessages"): ("Total",),
    ("microsoft.eventhub/namespaces", "OutgoingMessages"): ("Total",),
    ("microsoft.logic/workflows", "RunsStarted"): ("Total",),
    ("microsoft.logic/workflows", "RunsCompleted"): ("Total",),
    ("microsoft.apimanagement/service", "Requests"): ("Total", "Maximum", "Minimum"),
    ("microsoft.apimanagement/service", "Capacity"): ("Average", "Maximum"),
    ("microsoft.search/searchservices", "SearchQueriesPerSecond"): ("Average",),
    ("microsoft.search/searchservices", "ThrottledSearchQueriesPercentage"): ("Average",),
    ("microsoft.insights/components", "requests/count"): ("Count",),
    ("microsoft.insights/components", "availabilityResults/availabilityPercentage"): ("Average",),
    ("microsoft.operationalinsights/workspaces", "BillableIngestionGB"): ("Total",),
    ("microsoft.datafactory/factories", "PipelineSucceededRuns"): ("Total",),
    ("microsoft.datafactory/factories", "PipelineFailedRuns"): ("Total",),
    ("microsoft.kusto/clusters", "IngestionVolumeInMB"): ("Total", "Maximum"),
    ("microsoft.kusto/clusters", "QueryDuration"): ("Average", "Maximum", "Minimum", "Total"),
    ("microsoft.recoveryservices/vaults", "BackupHealthEvent"): ("Count",),
}


def normalize_arm_type(arm_type: str) -> str:
    return (arm_type or "").strip().lower()


def lookup_supported_aggregations(monitor_arm_type: str, metric_name: str) -> tuple[str, ...] | None:
    key = (normalize_arm_type(monitor_arm_type), metric_name)
    return METRIC_SUPPORTED_AGGREGATIONS.get(key)


def display_stats_from_azure_aggregations(
    supported: tuple[str, ...],
    *,
    primary_aggregation: str,
) -> tuple[str, ...]:
    """Map Azure aggregation names to display stat keys, primary first."""
    from app.resources.types import primary_stat_for_aggregation

    keys: list[str] = []
    for agg in supported:
        stat = AZURE_AGG_TO_STAT_KEY.get(agg)
        if stat and stat not in keys:
            keys.append(stat)
    primary = primary_stat_for_aggregation(primary_aggregation)
    if primary in keys:
        return tuple([primary] + [k for k in keys if k != primary])
    return tuple(keys)


def coerce_primary_aggregation(requested: str, supported: tuple[str, ...]) -> str:
    req = (requested or "Average").strip()
    if req in supported:
        return req
    return supported[0] if supported else "Average"


def fetch_aggregations_for_profile(metrics: tuple[UtilizationMetric, ...]) -> str:
    """Comma-separated Azure aggregations to request for a monitor profile."""
    ordered: list[str] = []
    seen: set[str] = set()
    for metric in metrics:
        for agg in metric.supported_aggregations:
            if agg not in seen:
                seen.add(agg)
                ordered.append(agg)
    return ",".join(ordered) if ordered else "Average,Minimum,Maximum,Total,Count"


AZURE_METRICS_DOC_BASE = (
    "https://learn.microsoft.com/en-us/azure/azure-monitor/reference/supported-metrics"
)


def azure_metrics_doc_url(doc_ref: str) -> str | None:
    """Full Learn URL for a resource type's supported-metrics page."""
    ref = (doc_ref or "").strip()
    if not ref:
        return None
    if ref.startswith("http://") or ref.startswith("https://"):
        return ref
    slug = ref if ref.endswith("-metrics") else f"{ref}-metrics"
    return f"{AZURE_METRICS_DOC_BASE}/{slug}"


def enrich_utilization_metric(
    monitor_arm_type: str,
    metric: UtilizationMetric,
) -> UtilizationMetric:
    """Apply Azure-doc supported aggregations and derived display metadata."""
    from dataclasses import replace

    from app.resources.types import infer_metric_metadata, primary_stat_for_aggregation

    supported = lookup_supported_aggregations(monitor_arm_type, metric.metric_name)
    if not supported:
        meta = infer_metric_metadata(metric.fact_key, metric.aggregation)
        fallback_agg = coerce_primary_aggregation(metric.aggregation, (metric.aggregation,))
        return replace(
            metric,
            supported_aggregations=(fallback_agg,),
            display_stats=metric.display_stats or tuple(meta["display_stats"]),  # type: ignore[arg-type]
            unit=metric.unit or str(meta["unit"]),
            primary_stat=metric.primary_stat or str(meta["primary_stat"]),
            impact=metric.impact or str(meta["impact"]),
        )

    aggregation = coerce_primary_aggregation(metric.aggregation, supported)
    meta = infer_metric_metadata(metric.fact_key, aggregation)
    display_stats = display_stats_from_azure_aggregations(supported, primary_aggregation=aggregation)
    return replace(
        metric,
        aggregation=aggregation,
        supported_aggregations=supported,
        display_stats=display_stats,
        unit=metric.unit or str(meta["unit"]),
        primary_stat=primary_stat_for_aggregation(aggregation),
        impact=metric.impact or str(meta["impact"]),
    )


def enrich_monitor_profile(profile: ResourceMonitorProfile) -> ResourceMonitorProfile:
    """Return profile with catalog-backed metric metadata."""
    from dataclasses import replace

    metrics = tuple(
        enrich_utilization_metric(profile.monitor_arm_type, m)
        for m in profile.metrics
    )
    return replace(profile, metrics=metrics)
