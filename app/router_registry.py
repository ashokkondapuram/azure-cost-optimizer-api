"""Central registration for all API routers (no /api prefix — mirrored in production)."""

from __future__ import annotations

from fastapi import FastAPI

from app.routers.activity import router as activity_router
from app.routers.admin import router as admin_router
from app.routers.auth import router as auth_router
from app.routers.budgets import router as budgets_router
from app.routers.carbon_footprint import router as carbon_router
from app.routers.cost_anomaly import router as cost_anomaly_router
from app.routers.costs import router as costs_router
from app.routers.dashboard import router as dashboard_router
from app.routers.engine_analysis import router as engine_analysis_router
from app.routers.events import router as events_router
from app.routers.global_health import router as global_health_router
from app.routers.idle_resources import router as idle_resources_router
from app.routers.k8s import router as k8s_router
from app.routers.maintenance import router as maintenance_router
from app.routers.metrics import router as metrics_router
from app.routers.optimize import router as optimize_router
from app.routers.quota import router as quota_router
from app.routers.reservation_coverage import router as reservation_router
from app.routers.resource_types import router as resource_types_router
from app.routers.resources import router as resources_router
from app.routers.resources_inventory import router as resources_inventory_router
from app.routers.savings_planner import router as savings_planner_router
from app.routers.scheduler_status import router as scheduler_router
from app.routers.sync import router as sync_router
from app.routers.pipeline import router as pipeline_router
from app.routers.security_posture import router as security_posture_router
from app.routers.settings import router as settings_router
import structlog

log = structlog.get_logger()


def register_api_routers(app: FastAPI) -> None:
    """Mount all domain routers on the FastAPI application."""
    routers = [
        auth_router,
        settings_router,
        costs_router,
        dashboard_router,
        sync_router,
        resource_types_router,
        resources_router,
        resources_inventory_router,
        optimize_router,
        activity_router,
        idle_resources_router,
        cost_anomaly_router,
        savings_planner_router,
        engine_analysis_router,
        reservation_router,
        budgets_router,
        quota_router,
        security_posture_router,
        admin_router,
        maintenance_router,
        global_health_router,
        scheduler_router,
        pipeline_router,
        carbon_router,
        metrics_router,
        events_router,
        k8s_router,
    ]
    for router in routers:
        app.include_router(router)
    log.info("api_routers_registered", count=len(routers))
