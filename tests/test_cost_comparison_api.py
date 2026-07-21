"""Tests for GET /costs/comparison route registration."""

from fastapi.routing import APIRoute

from app.routers.costs import router as costs_router


def test_cost_comparison_route_registered():
    paths = [route.path for route in costs_router.routes if isinstance(route, APIRoute)]
    assert "/costs/comparison" in paths
