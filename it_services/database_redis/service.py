"""IT service entity — public exports for Azure Cache for Redis."""

from __future__ import annotations

SERVICE_ID = "database-redis"
CANONICAL_TYPE = "database/redis"
ARM_TYPE = "Microsoft.Cache/redis"
DISPLAY_NAME = "Azure Cache for Redis"
API_SLUG = "redis"
COMPONENT = "Redis Cache"

from it_services.database_redis.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.database_redis.engine.sub_engine import RedisSubEngine as SubEngine

