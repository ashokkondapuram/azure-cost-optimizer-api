"""FastAPI factory for per-resource microservices."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import unquote

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from costoptimizer_core.contracts import (
    AnalyzeRequest,
    AnalyzeResponse,
    HealthResponse,
    MetricsCollectRequest,
    MetricsCollectResponse,
    ServiceMetaResponse,
    SyncRequest,
    SyncResponse,
)
from costoptimizer_core.registry import ServiceConfig


def _ensure_repo_path() -> None:
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)


def create_resource_service(config: ServiceConfig) -> FastAPI:
    _ensure_repo_path()

    from app.auth import arm_bearer_token
    from app.database import get_db
    from app.db_sync import sync_scoped
    from app.db_analyze import run_db_analysis
    from app.cost_db import resource_cost_map_from_db
    from app.perf_cache import cached_cost_map
    from app.resource_list_enrichment import enrich_resource_list_result
    from app.resource_store import get_resources_db, get_resources_db_page
    from app.resources.registry import get_technical_fetch_spec

    app = FastAPI(
        title=f"CostOptimizer — {config.display_name or config.service_id}",
        version="1.0.0",
    )

    @app.get("/health/live", response_model=HealthResponse)
    def health_live() -> HealthResponse:
        return HealthResponse(service_id=config.service_id)

    @app.get("/v1/meta", response_model=ServiceMetaResponse)
    def meta() -> ServiceMetaResponse:
        return ServiceMetaResponse(
            service_id=config.service_id,
            canonical_type=config.canonical_type,
            api_slug=config.api_slug,
            component=config.component,
            arm_type=config.arm_type,
            display_name=config.display_name,
            migrated=config.migrated,
        )

    @app.get("/v1/resources")
    def list_resources(
        request: Request,
        subscription_id: str = Query(...),
        source: str = Query("db"),
        limit: int | None = Query(None, ge=1, le=200),
        offset: int = Query(0, ge=0),
        include_costs: bool = Query(
            True,
            description="Attach MTD billed cost from PostgreSQL (default true).",
        ),
        include_metrics: bool = Query(
            False,
            description="Include computed disk metrics when supported.",
        ),
        db: Session = Depends(get_db),
    ):
        if source != "db":
            raise HTTPException(400, "Only source=db is supported in microservice mode")
        sub = subscription_id.strip().lower()
        include_properties = request.query_params.get("include_properties", "").lower() in {
            "1", "true", "yes",
        }
        cost_map = None
        if include_costs:
            cost_map = cached_cost_map(
                f"cost_map:{sub}",
                lambda: resource_cost_map_from_db(db, sub),
            )
        if limit is not None:
            from app.pagination import validate_pagination

            cursor = (request.query_params.get("cursor") or "").strip() or None
            pg = validate_pagination(limit, offset, cursor=cursor)
            result = get_resources_db_page(
                db,
                sub,
                config.canonical_type,
                limit=pg.limit,
                offset=pg.offset,
                cursor=pg.cursor,
                include_properties=include_properties,
                cost_map=cost_map,
            )
        else:
            result = get_resources_db(
                db,
                sub,
                config.canonical_type,
                include_properties=include_properties,
                cost_map=cost_map,
            )
        return enrich_resource_list_result(
            result,
            resource_type=config.canonical_type,
            include_metrics=include_metrics,
        )

    @app.get("/v1/resources/{resource_id:path}")
    def get_resource(
        resource_id: str,
        subscription_id: str = Query(...),
        include_costs: bool = Query(True),
        include_metrics: bool = Query(False),
        db: Session = Depends(get_db),
    ):
        rid = unquote(resource_id)
        sub = subscription_id.strip().lower()
        cost_map = None
        if include_costs:
            cost_map = cached_cost_map(
                f"cost_map:{sub}",
                lambda: resource_cost_map_from_db(db, sub),
            )
        rows = get_resources_db(
            db,
            sub,
            config.canonical_type,
            include_properties=True,
            cost_map=cost_map,
        )
        iterable = rows if isinstance(rows, list) else rows.get("items", [])
        for row in iterable:
            if (row.get("id") or "").lower() == rid.lower():
                enriched = enrich_resource_list_result(
                    [row],
                    resource_type=config.canonical_type,
                    include_metrics=include_metrics,
                )
                return enriched[0]
        raise HTTPException(404, "Resource not found")

    @app.post("/v1/sync", response_model=SyncResponse)
    def sync_resources(
        body: SyncRequest,
        db: Session = Depends(get_db),
        token: str = Depends(arm_bearer_token),
    ):
        sub = body.subscription_id.strip().lower()
        result = sync_scoped(
            sub,
            db,
            token,
            [config.canonical_type],
            include_costs=body.include_costs,
        )
        return SyncResponse(
            subscription_id=sub,
            canonical_type=config.canonical_type,
            resource_counts=result.get("resource_counts") or {},
            cost_counts=result.get("cost_counts") or {},
        )

    @app.post("/v1/analyze", response_model=AnalyzeResponse)
    def analyze_resources(
        body: AnalyzeRequest,
        db: Session = Depends(get_db),
        token: str = Depends(arm_bearer_token),
    ):
        sub = body.subscription_id.strip().lower()
        if body.refresh_azure_costs:
            from app.db_sync import sync_costs

            try:
                sync_costs(sub, db, token)
            except Exception:
                pass
        try:
            result = run_db_analysis(
                db,
                subscription_id=sub,
                profile=body.profile,
                engine_version=body.engine_version,
                scope_resource_types=[config.canonical_type],
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        findings = result.get("findings") or []
        return AnalyzeResponse(
            subscription_id=sub,
            canonical_type=config.canonical_type,
            component=config.component,
            findings_count=len(findings) if isinstance(findings, list) else int(result.get("findings_count") or 0),
            result=result,
        )

    @app.get("/v1/rules")
    def list_rules() -> dict[str, Any]:
        spec = get_technical_fetch_spec(config.canonical_type)
        rules: list[str] = []
        if spec:
            for field_def in spec.fields:
                rules.extend(field_def.rules)
            for metric in spec.usage_metrics:
                rules.extend(metric.rules)
        return {
            "canonical_type": config.canonical_type,
            "component": config.component,
            "rules": sorted(set(rules)),
        }

    @app.post("/v1/metrics/collect", response_model=MetricsCollectResponse)
    def collect_metrics(
        body: MetricsCollectRequest,
        db: Session = Depends(get_db),
        token: str = Depends(arm_bearer_token),
    ):
        from app.metrics_api import fetch_metrics_for_subscription

        sub = body.subscription_id.strip().lower()
        stats = fetch_metrics_for_subscription(
            db,
            sub,
            token=token,
            resource_types=[config.canonical_type],
            resource_ids=body.resource_ids or None,
        )
        return MetricsCollectResponse(
            subscription_id=sub,
            collected=int(stats.get("resources_processed") or stats.get("collected") or 0),
            stats=stats,
        )

    @app.exception_handler(Exception)
    def unhandled_error(_request: Request, exc: Exception) -> JSONResponse:
        if os.getenv("DEBUG_MICROSERVICES") == "1":
            raise exc
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app
