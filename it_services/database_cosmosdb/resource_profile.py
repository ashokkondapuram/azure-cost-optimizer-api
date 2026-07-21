"""Resource profile — owned by database-cosmosdb IT service."""

from app.resources.types import TechnicalFetchSpec, field

from it_services.database_cosmosdb.assessment_bridge import (
    build_cosmos_monitor_profile,
    cosmos_sync_property_paths,
)

CANONICAL_TYPE = "database/cosmosdb"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.DocumentDB/databaseAccounts",
    display_name="Cosmos DB account",
    sync_property_paths=cosmos_sync_property_paths(),
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

MONITOR_PROFILE = build_cosmos_monitor_profile()
