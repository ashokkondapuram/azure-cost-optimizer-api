from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "search/cognitivesearch"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Search/searchServices",
    display_name="Cognitive Search",
    sync_property_paths=("provisioningState", "replicaCount", "partitionCount"),
    generic_arm_sync=True,
    fields=(
        field("replica_count", "props:replicaCount", "Replica count", "capacity", "COST_SEARCH_REVIEW"),
        field("partition_count", "props:partitionCount", "Partition count", "capacity", "COST_SEARCH_REVIEW"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.search/searchservices",
    canonical_type=CANONICAL_TYPE,
    display_name="Cognitive Search",
    doc_ref="microsoft-search-searchservices-metrics",
    metrics=(
        um("SearchQueriesPerSecond", "search_qps", "Search queries per second", aggregation="Average",
           rules=("COST_SEARCH_REVIEW",)),
        um("ThrottledSearchQueriesPercentage", "throttled_search_pct", "Throttled search queries",
           rules=("COST_SEARCH_REVIEW",)),
    ),
)
