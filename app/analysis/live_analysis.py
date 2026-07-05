"""Live analysis orchestration — extracted from main.py.

This module owns the _run_live_analysis pipeline that:
  1. Fetches 20+ ARM resource types in parallel (ThreadPoolExecutor)
  2. Enriches each resource with ARM properties
  3. Loads Azure Monitor metrics
  4. Runs the OptimizationEngine / ExtendedOptimizationEngine
  5. Optionally enriches findings with AI
  6. Persists the OptimizationRun to the database

It was previously inlined inside app/main.py as a private helper function,
which violated the principle that routing files should not contain business
logic. The public entry-point is `run_live_analysis()`.
"""
from __future__ import annotations

import concurrent.futures
from typing import Any, Optional

import structlog
from sqlalchemy.orm import Session

from app.analysis_persist import persist_optimization_run
from app.arm_resource_enrichment import enrich_arm_resources_for_type
from app.ai_analysis import enrich_analysis_with_ai
from app.optimizer.engine import OptimizationEngine
from app.optimizer.extended_engine import ExtendedOptimizationEngine
from app.optimizer.engine_config import get_effective_config
from app.optimizer.unified_engine import append_cost_export_findings
from app.resources import list_technical_fetch_specs
from app.http_client import AzureAPIError, arm_fetch_workers

log = structlog.get_logger()


def run_live_analysis(
    db: Session,
    subscription_id: str,
    *,
    profile: str = "default",
    engine_version: str = "extended",
    rule_overrides: dict | None = None,
    components: list[str] | None = None,
    include_metrics: bool = True,
    include_ai: bool = True,
    timespan_metrics: str = "P7D",
    token: str | None = None,
) -> dict[str, Any]:
    """Fetch all ARM resource types live and run the optimization engine.

    Returns the serialised OptimizationRun result dict (same shape as the
    DB-backed run_db_analysis response).

    Auth failures (HTTP 401/403) are surfaced as HTTPException(401/503) so
    that the caller can distinguish them from transient fetch errors, which
    are logged as warnings and treated as empty resource lists.
    """
    from app.auth import arm_auth_context
    from app.azure_resources import AzureResourcesClient
    from app.cost_db import resource_cost_map_from_db
    from app.cost_utils import resource_cost_billing_from_map

    rule_overrides = rule_overrides or {}
    errors: dict[str, str] = {}
    fetched: dict[str, list] = {}

    fetch_specs = list_technical_fetch_specs()
    if components:
        fetch_specs = [s for s in fetch_specs if s.get("component") in set(components)]

    # ── parallel ARM fetch ────────────────────────────────────────────────
    def _fetch_one(spec: dict) -> tuple[str, list]:
        key = spec["key"]
        try:
            with arm_auth_context(db=db, token=token):
                client = AzureResourcesClient(db=db)
                items = client.list_resources_by_type(subscription_id, spec["arm_type"])
            enriched = enrich_arm_resources_for_type(items, spec["key"], db=db)
            return key, enriched
        except AzureAPIError as exc:
            # Distinguish auth failures from transient errors.
            if exc.status in {401, 403}:
                log.error(
                    "live_analysis.auth_failure",
                    resource=key,
                    status=exc.status,
                    error=str(exc)[:300],
                )
                raise
            log.warning("live_analysis.fetch_failed", resource=key, error=str(exc)[:300])
            return key, []
        except Exception as exc:
            log.warning("live_analysis.fetch_failed", resource=key, error=str(exc)[:300])
            return key, []

    max_workers = arm_fetch_workers()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_one, spec): spec["key"] for spec in fetch_specs}
        for future in concurrent.futures.as_completed(futures):
            key = futures[future]
            try:
                k, resources = future.result()
                fetched[k] = resources
            except AzureAPIError as exc:
                if exc.status in {401, 403}:
                    # Auth failure — abort the whole run immediately.
                    from fastapi import HTTPException
                    raise HTTPException(
                        status_code=401,
                        detail=f"Azure authentication failed during live analysis: {exc.message}",
                    ) from exc
                errors[key] = str(exc)
                fetched[key] = []
            except Exception as exc:
                errors[key] = str(exc)
                fetched[key] = []

    # ── metrics ───────────────────────────────────────────────────────────
    if include_metrics:
        try:
            from app.azure_monitor_aggregations import load_metrics_for_resources
            for key, resources in fetched.items():
                if resources:
                    fetched[key] = load_metrics_for_resources(
                        resources, timespan=timespan_metrics, db=db, token=token,
                    )
        except Exception as exc:
            log.warning("live_analysis.metrics_failed", error=str(exc)[:300])

    # ── cost map ─────────────────────────────────────────────────────────
    cost_map = resource_cost_map_from_db(db, subscription_id)
    for key, resources in fetched.items():
        fetched[key] = resource_cost_billing_from_map(resources, cost_map)

    # ── engine ────────────────────────────────────────────────────────────
    cfg = get_effective_config(db, profile=profile)
    if rule_overrides:
        cfg["rule_overrides"] = {**cfg.get("rule_overrides", {}), **rule_overrides}

    if engine_version == "extended":
        engine = ExtendedOptimizationEngine(config=cfg)
    else:
        engine = OptimizationEngine(config=cfg)

    findings = engine.analyze(fetched)
    findings = append_cost_export_findings(findings, db, subscription_id)

    # ── AI enrichment ─────────────────────────────────────────────────────
    if include_ai:
        try:
            findings = enrich_analysis_with_ai(findings, db=db)
        except Exception as exc:
            log.warning("live_analysis.ai_enrichment_failed", error=str(exc)[:300])

    # ── persist ───────────────────────────────────────────────────────────
    run_id = persist_optimization_run(
        db,
        subscription_id=subscription_id,
        findings=findings,
        profile=profile,
        source="live",
        fetch_errors=errors if errors else None,
    )

    log.info(
        "live_analysis.complete",
        subscription_id=subscription_id,
        run_id=run_id,
        findings=len(findings),
        errors=len(errors),
    )

    return {
        "run_id": run_id,
        "subscription_id": subscription_id,
        "source": "live",
        "profile": profile,
        "engine_version": engine_version,
        "findings_count": len(findings),
        "findings": findings,
        "fetch_errors": errors,
    }
