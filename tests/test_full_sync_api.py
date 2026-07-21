"""Tests for sync API route registration."""


def test_sync_router_registers_pipeline_status_route():
    from app.routers.sync import router

    paths = {route.path for route in router.routes}
    assert "/sync/full" in paths
    assert "/sync/pipeline" in paths
    assert "/sync/progress" in paths
    assert "/sync/progress/stream" in paths


def test_resources_inventory_registers_sync_route():
    from app.routers.resources_inventory import router

    sync_routes = [route for route in router.routes if getattr(route, "path", "") == "/resources/sync"]
    assert sync_routes
    assert sync_routes[0].status_code == 202
