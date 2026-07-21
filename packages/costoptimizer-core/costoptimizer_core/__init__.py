"""CostOptimizeRecommender shared microservice library."""

from costoptimizer_core.registry import (
    MIGRATED_SERVICES,
    ServiceConfig,
    all_service_configs,
    get_service_by_api_slug,
    get_service_config,
    service_id_for_canonical,
)
from costoptimizer_core.resource_app import create_resource_service

__all__ = [
    "MIGRATED_SERVICES",
    "ServiceConfig",
    "all_service_configs",
    "create_resource_service",
    "get_service_by_api_slug",
    "get_service_config",
    "service_id_for_canonical",
]
