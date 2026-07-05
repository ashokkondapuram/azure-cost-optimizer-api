from app.resources.types import ResourceMonitorProfile, TechnicalFetchSpec, field, utilization_metric as um

CANONICAL_TYPE = "database/redis"

TECHNICAL_FETCH_SPEC = TechnicalFetchSpec(
    canonical_type=CANONICAL_TYPE,
    arm_type="Microsoft.Cache/redis",
    display_name="Azure Cache for Redis",
    sync_property_paths=(
        "redisVersion", "redisConfiguration", "enableNonSslPort",
        "provisioningState", "shardCount", "replicasPerMaster",
    ),
    fields=(
        field("redis_version", "props:redisVersion", "Redis version", "configuration"),
        field("maxmemory_policy", "props:redisConfiguration.maxmemoryPolicy", "Eviction policy", "configuration",
              "REDIS_TIER_REVIEW"),
        field("shard_count", "props:shardCount", "Shard count", "capacity", "REDIS_TIER_REVIEW"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.cache/redis",
    canonical_type=CANONICAL_TYPE,
    display_name="Azure Cache for Redis",
    doc_ref="microsoft-cache-redis-metrics",
    metrics=(
        um("usedmemorypercentage", "memory_pct", "Redis memory utilization", aggregation="Maximum",
           rules=("REDIS_TIER_REVIEW", "REDIS_RIGHTSIZE_EXTENDED")),
        um("cachehits", "cache_hits", "Redis cache hits", aggregation="Total",
           rules=("REDIS_HEALTH_EXTENDED",)),
        um("operationsPerSecond", "ops_per_sec", "Redis operations per second", aggregation="Maximum",
           rules=("REDIS_HEALTH_EXTENDED",)),
    ),
)
