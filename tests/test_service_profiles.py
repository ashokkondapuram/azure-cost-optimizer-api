"""Service profile router bundles."""

from app.service_profiles import routers_for_profile


def test_metrics_profile_loads_metrics_router_only():
    routers = routers_for_profile("metrics")
    assert len(routers) == 1
    assert routers[0].prefix == "/metrics"


def test_analysis_profile_excludes_metrics_router():
    routers = routers_for_profile("analysis")
    prefixes = {router.prefix for router in routers}
    assert "/metrics" not in prefixes
    assert "/events" in prefixes
    assert len(routers) == 6


def test_inventory_profile_includes_sync_and_dashboard_routes():
    routers = routers_for_profile("inventory")
    route_paths = {
        getattr(route, "path", "")
        for router in routers
        for route in router.routes
    }
    assert "/sync/pipeline" in route_paths
    assert "/resources/sync" in route_paths
    assert "/sync/status" in route_paths
    assert "/dashboard/overview" in route_paths
    assert len(routers) == 6


def test_core_profile_includes_auth_and_admin():
    routers = routers_for_profile("core")
    prefixes = {router.prefix for router in routers}
    assert "/auth" in prefixes
    assert "/settings" in prefixes
    assert "/admin" in prefixes
    assert len(routers) >= 8
