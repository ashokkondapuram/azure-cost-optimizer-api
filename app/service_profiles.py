"""Router bundles for platform microservice entrypoints (Option A — same codebase).

Routers are imported lazily per profile so cost does not pull analysis
dependencies and inventory does not pull unrelated domains at startup.
"""

from __future__ import annotations

from importlib import import_module

from fastapi import APIRouter

# (module_path, router attribute) — loaded only when a profile is registered.
_PROFILE_ROUTER_SPECS: dict[str, tuple[tuple[str, str], ...]] = {
    "auth": (("app.routers.auth", "router"),),
    "cost": (
        ("app.routers.costs", "router"),
        ("app.routers.cost_dashboard_paths", "router"),
        ("app.routers.budgets", "router"),
        ("app.routers.cost_anomaly", "router"),
        ("app.routers.reservation_coverage", "router"),
        ("app.routers.savings_planner", "router"),
        ("app.routers.carbon_footprint", "router"),
    ),
    "analysis": (
        ("app.routers.optimize", "router"),
        ("app.routers.engine_analysis", "router"),
        ("app.routers.idle_resources", "router"),
        ("app.routers.pipeline", "router"),
        ("app.routers.events", "router"),
        ("app.routers.activity", "router"),
    ),
    "metrics": (
        ("app.routers.metrics", "router"),
    ),
    "inventory": (
        ("app.routers.resources", "router"),
        ("app.routers.resources_inventory", "router"),
        ("app.routers.resource_types", "router"),
        ("app.routers.scheduler_status", "router"),
        ("app.routers.sync", "router"),
        ("app.routers.dashboard", "router"),
    ),
    "core": (
        ("app.routers.auth", "router"),
        ("app.routers.settings", "router"),
        ("app.routers.admin", "router"),
        ("app.routers.k8s", "router"),
        ("app.routers.maintenance", "router"),
        ("app.routers.global_health", "router"),
        ("app.routers.quota", "router"),
        ("app.routers.security_posture", "router"),
    ),
}


def _import_router(module_path: str, attr: str) -> APIRouter:
    module = import_module(module_path)
    return getattr(module, attr)


def routers_for_profile(profile: str) -> tuple[APIRouter, ...]:
    try:
        specs = _PROFILE_ROUTER_SPECS[profile]
    except KeyError as exc:
        raise ValueError(f"Unknown service profile: {profile!r}") from exc
    return tuple(_import_router(mod, attr) for mod, attr in specs)


def register_profile_routers(app, profile: str) -> int:
    """Mount all routers for a platform service profile."""
    routers = routers_for_profile(profile)
    for router in routers:
        app.include_router(router)
    return len(routers)
