from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "database/cosmosdb"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.DocumentDB/databaseAccounts",
    display_name="Cosmos DB account",
    sync_property_paths=(
        "databaseAccountOfferType", "capabilities", "enableAutomaticFailover",
        "provisioningState", "enableFreeTier",
    ),
    fields=(
        field("serverless_enabled", "computed:serverless_enabled", "Serverless enabled", "configuration",
              "COSMOS_SERVERLESS"),
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
           rules=("COSMOS_SERVERLESS", "COSMOS_AUTOSCALE_EXTENDED")),
        um("TotalRequestUnits", "total_ru", "Cosmos DB request units consumed", aggregation="Total",
           rules=("COSMOS_AUTOSCALE_EXTENDED",)),
    ),
)
