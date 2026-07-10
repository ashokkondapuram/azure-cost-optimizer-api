"""Resource profile — owned by database-cosmosdb IT service."""

from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "database/cosmosdb"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.DocumentDB/databaseAccounts",
    display_name="Cosmos DB account",
    sync_property_paths=(
        "databaseAccountOfferType", "capabilities", "enableAutomaticFailover",
        "enableMultipleWriteLocations", "enableFreeTier", "consistencyPolicy",
        "locations", "provisioningState",
    ),
    fields=(
        field("serverless_enabled", "computed:serverless_enabled", "Serverless enabled", "configuration",
              "COSMOS_SERVERLESS", "COSMOS_AUTOSCALE_EXTENDED", "COSMOS_PROVISIONED_EXTENDED"),
        field("api_type", "computed:cosmos_api_type", "API type", "configuration",
              "COSMOS_API_COST_VARIANCE"),
        field("consistency_level", "props:consistencyPolicy.defaultConsistencyLevel", "Consistency level", "configuration",
              "COSMOS_CONSISTENCY_OVERPROVISIONED"),
        field("region_count", "computed:cosmos_region_count", "Region count", "configuration",
              "COSMOS_MULTI_WRITE_UNNECESSARY"),
        field("multi_write_enabled", "props:enableMultipleWriteLocations", "Multi-region writes", "configuration",
              "COSMOS_MULTI_WRITE_UNNECESSARY"),
        field("free_tier_enabled", "props:enableFreeTier", "Free tier", "configuration",
              "COSMOS_FREE_TIER_SUBOPTIMAL"),
        field("automatic_failover_enabled", "props:enableAutomaticFailover", "Automatic failover", "configuration",
              "COSMOS_FAILOVER_UNNECESSARY"),
        field("offer_type", "props:databaseAccountOfferType", "Offer type", "configuration"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.documentdb/databaseaccounts",
    canonical_type=CANONICAL_TYPE,
    display_name="Cosmos DB account",
    doc_ref="microsoft-documentdb-databaseaccounts-metrics",
    metrics=(
        um("TotalRequests", "request_count", "Cosmos DB request volume", aggregation="Count",
           rules=(
               "COSMOS_SERVERLESS", "COSMOS_AUTOSCALE_EXTENDED",
           )),
        um("TotalRequestUnits", "total_ru", "Cosmos DB request units consumed", aggregation="Total",
           rules=(
               "COSMOS_AUTOSCALE_EXTENDED", "COSMOS_SERVERLESS", "COSMOS_FREE_TIER_SUBOPTIMAL",
           )),
        um("NormalizedRUConsumption", "normalized_ru_pct", "Normalized RU consumption",
           aggregation="Average",
           rules=(
               "COSMOS_AUTOSCALE_EXTENDED", "COSMOS_RU_RIGHT_SIZING_UNDER",
               "COSMOS_RU_RIGHT_SIZING_OVER", "COSMOS_THROTTLING_DETECTED",
               "COSMOS_RESERVED_CAPACITY_ELIGIBLE",
           )),
        um("NormalizedRUConsumption", "normalized_ru_peak_pct", "Peak normalized RU consumption",
           aggregation="Maximum",
           rules=("COSMOS_THROTTLING_DETECTED", "COSMOS_HOT_CONTAINER_DETECTED")),
        um("ProvisionedThroughput", "provisioned_throughput", "Provisioned throughput",
           aggregation="Maximum",
           rules=("COSMOS_RU_RIGHT_SIZING_UNDER", "COSMOS_FREE_TIER_SUBOPTIMAL")),
        um("DataUsage", "data_usage_bytes", "Data usage", aggregation="Total",
           rules=("COSMOS_LARGE_ITEMS_DETECTED", "COSMOS_INDEXING_OVERPROVISIONED")),
        um("IndexUsage", "index_usage_bytes", "Index usage", aggregation="Total",
           rules=("COSMOS_INDEXING_OVERPROVISIONED",)),
        um("DocumentCountV2", "document_count", "Document count", aggregation="Total",
           rules=("COSMOS_LARGE_ITEMS_DETECTED",)),
        um("ReplicationLatency", "replication_latency_ms", "Replication latency",
           aggregation="Maximum",
           rules=("COSMOS_MULTI_WRITE_UNNECESSARY",)),
        um("ServerSideLatencyDirect", "server_latency_ms", "Server-side latency (direct)",
           aggregation="Average",
           rules=("COSMOS_THROTTLING_DETECTED",)),
    ),
)
