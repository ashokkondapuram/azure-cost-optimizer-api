"""Events SSE route registration."""

from fastapi.routing import APIRoute

from app.routers.events import router


def test_job_events_route_path_not_doubled():
    paths = [route.path for route in router.routes if isinstance(route, APIRoute)]
    assert "/events/jobs/{subscription_id}" in paths
    assert "/events/events/jobs/{subscription_id}" not in paths
