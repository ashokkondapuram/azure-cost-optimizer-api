"""Resource profile — owned by database-redis IT service."""

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
              "REDIS_TIER_REVIEW", "REDIS_HIT_RATIO_POOR"),
        field("shard_count", "props:shardCount", "Shard count", "capacity",
              "REDIS_TIER_REVIEW", "REDIS_CLUSTER_UNNECESSARY"),
        field("rdb_backup_enabled", "props:redisConfiguration.rdbBackupEnabled", "RDB backup", "configuration",
              "REDIS_PERSISTENCE_REVIEW"),
        field("aof_backup_enabled", "props:redisConfiguration.aofBackupEnabled", "AOF backup", "configuration",
              "REDIS_PERSISTENCE_REVIEW"),
    ),
)

MONITOR_PROFILE = ResourceMonitorProfile(
    monitor_arm_type="microsoft.cache/redis",
    canonical_type=CANONICAL_TYPE,
    display_name="Azure Cache for Redis",
    doc_ref="microsoft-cache-redis-metrics",
    metrics=(
        um("usedmemorypercentage", "memory_pct", "Redis memory utilization", aggregation="Maximum",
           rules=(
               "REDIS_TIER_REVIEW", "REDIS_RIGHTSIZE_EXTENDED", "REDIS_MEMORY_PRESSURE",
               "REDIS_LOW_UTILIZATION",
           )),
        um("cachehits", "cache_hits", "Redis cache hits", aggregation="Total",
           rules=("REDIS_HEALTH_EXTENDED", "REDIS_HIT_RATIO_POOR")),
        um("cachemisses", "cache_misses", "Redis cache misses", aggregation="Total",
           rules=("REDIS_HIT_RATIO_POOR",)),
        um("cachemissrate", "cache_miss_rate_pct", "Cache miss rate", aggregation="Average",
           rules=("REDIS_HIT_RATIO_POOR",)),
        um("operationsPerSecond", "ops_per_sec", "Redis operations per second", aggregation="Maximum",
           rules=("REDIS_HEALTH_EXTENDED", "REDIS_IDLE_DETECTION", "REDIS_CLUSTER_UNNECESSARY")),
        um("serverLoad", "server_load_pct", "Redis server load", aggregation="Maximum",
           rules=("REDIS_LOW_UTILIZATION",)),
        um("evictedkeys", "evicted_keys", "Evicted keys", aggregation="Total",
           rules=("REDIS_MEMORY_PRESSURE", "REDIS_LOW_UTILIZATION")),
        um("expiredkeys", "expired_keys", "Expired keys", aggregation="Total",
           rules=("REDIS_MEMORY_PRESSURE",)),
        um("connectedclients", "connected_clients", "Connected clients", aggregation="Maximum",
           rules=("REDIS_TIER_REVIEW",)),
        um("percentProcessorTime", "cpu_pct", "Redis CPU utilization", aggregation="Maximum",
           rules=("REDIS_LOW_UTILIZATION",)),
        um("errors", "error_count", "Redis errors", aggregation="Maximum",
           rules=("REDIS_HEALTH_EXTENDED",)),
        um("totalkeys", "total_keys", "Total keys", aggregation="Maximum",
           rules=("REDIS_TIER_REVIEW",)),
        um("usedmemoryRss", "used_memory_rss_bytes", "Used memory RSS", aggregation="Maximum",
           rules=("REDIS_MEMORY_PRESSURE",)),
    ),
)
