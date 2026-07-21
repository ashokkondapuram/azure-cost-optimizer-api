"""Orchestrate Azure properties, cost, metrics, advisors, and analysis into enrichment tables."""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any, Callable

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.cost_db import resource_cost_map_from_db
from app.data_store.resource_enrichment import (
    advisor_items_for_resource,
    sync_advisor_enrichment_for_subscription,
    sync_cost_for_subscription,
    sync_properties_for_subscription,
    sync_recommendations_from_snapshots,
    upsert_advisor_enrichment,
    upsert_cost,
    upsert_properties,
)
from app.focus_mapping import normalize_arm_id
from app.models import ResourceSnapshot

log = structlog.get_logger(__name__)


def _env_bool(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() not in {"0", "false", "no", "off"}


def enrichment_sync_enabled() -> bool:
    return _env_bool("SYNC_ENRICH_ENABLED", "true")


def enrichment_async_enabled() -> bool:
    return _env_bool("SYNC_ENRICH_ASYNC", "true")


def enrichment_timeout_sec() -> int:
    try:
        return max(30, int(os.getenv("SYNC_ENRICH_TIMEOUT_SEC", "300")))
    except (TypeError, ValueError):
        return 300


@dataclass(frozen=True)
class SyncStages:
    """Configurable enrichment stages (properties always run)."""

    properties: bool = True
    cost: bool = True
    metrics: bool = True
    advisors: bool = True
    analysis: bool = True

    @classmethod
    def from_env(cls) -> SyncStages:
        return cls(
            properties=True,
            cost=_env_bool("SYNC_ENRICH_COST", "true"),
            metrics=_env_bool("SYNC_ENRICH_METRICS", "true"),
            advisors=_env_bool("SYNC_ENRICH_ADVISORS", "true"),
            analysis=_env_bool("SYNC_ENRICH_ANALYSIS", "true"),
        )


def _resolve_snapshot(
    db: Session,
    subscription_id: str,
    resource_id: str | None = None,
    *,
    arm_id: str | None = None,
) -> ResourceSnapshot | None:
    sub = subscription_id.strip().lower()
    rid = normalize_arm_id(arm_id or resource_id or "")
    if not rid:
        return None
    return (
        db.query(ResourceSnapshot)
        .filter(
            ResourceSnapshot.subscription_id == sub,
            func.lower(ResourceSnapshot.resource_id) == rid,
            ResourceSnapshot.is_active.is_(True),
        )
        .first()
    )


def _run_with_timeout(
    fn: Callable[[], Any],
    *,
    timeout_sec: int,
    stage: str,
) -> dict[str, Any]:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn)
        try:
            result = future.result(timeout=timeout_sec)
            if isinstance(result, dict):
                return result
            return {"status": "ok", "result": result}
        except FuturesTimeoutError:
            log.warning("sync_enrich_stage_timeout", stage=stage, timeout_sec=timeout_sec)
            return {"status": "timeout", "stage": stage, "timeout_sec": timeout_sec}
        except Exception as exc:
            log.warning("sync_enrich_stage_failed", stage=stage, error=str(exc)[:300])
            return {"status": "error", "stage": stage, "error": str(exc)[:300]}


def _stage_properties(
    db: Session,
    subscription_id: str,
    snapshot: ResourceSnapshot,
) -> dict[str, Any]:
    upsert_properties(db, snapshot)
    return {"status": "ok", "arm_id": snapshot.resource_id}


def _stage_cost(
    db: Session,
    subscription_id: str,
    snapshot: ResourceSnapshot,
) -> dict[str, Any]:
    sub = subscription_id.strip().lower()
    cost_map = resource_cost_map_from_db(db, sub)
    arm = normalize_arm_id(snapshot.resource_id)
    overlay = cost_map.get(arm.lower()) or cost_map.get(arm)
    upsert_cost(db, snapshot, cost_overlay=overlay)
    return {"status": "ok", "arm_id": arm, "has_overlay": bool(overlay)}


def _stage_metrics(
    db: Session,
    subscription_id: str,
    snapshot: ResourceSnapshot,
    *,
    token: str | None,
) -> dict[str, Any]:
    from app.metrics_api import fetch_metrics_for_resource

    result = fetch_metrics_for_resource(
        snapshot.resource_id,
        db=db,
        refresh=True,
    )
    return {
        "status": "ok" if result.get("ok") else "empty",
        "arm_id": snapshot.resource_id,
        "data_quality": result.get("data_quality"),
        "ok": bool(result.get("ok")),
    }


def _stage_advisors(
    db: Session,
    subscription_id: str,
    snapshot: ResourceSnapshot,
    *,
    token: str | None,
) -> dict[str, Any]:
    items = advisor_items_for_resource(db, subscription_id, snapshot.resource_id)
    upsert_advisor_enrichment(db, snapshot, advisor_items=items)
    return {"status": "ok", "arm_id": snapshot.resource_id, "advisor_count": len(items)}


def _stage_analysis(
    db: Session,
    subscription_id: str,
    snapshot: ResourceSnapshot,
) -> dict[str, Any]:
    from app.analysis import run_db_analysis
    from app.analysis_persist import refresh_resource_analysis_summary

    sub = subscription_id.strip().lower()
    arm = normalize_arm_id(snapshot.resource_id)
    analysis = run_db_analysis(
        db,
        subscription_id=sub,
        scope_resource_ids=[arm],
        fetch_monitor_metrics=False,
        include_ai=False,
    )
    refresh_resource_analysis_summary(db, subscription_id=sub, resource_id=arm)
    return {
        "status": analysis.get("status", "ok"),
        "arm_id": arm,
        "findings": analysis.get("findings_count") or analysis.get("total_findings"),
    }


def sync_resource_full(
    db: Session,
    subscription_id: str,
    *,
    resource_id: str | None = None,
    arm_id: str | None = None,
    token: str | None = None,
    stages: SyncStages | None = None,
    timeout_sec: int | None = None,
) -> dict[str, Any]:
    """Run enrichment stages for one inventory row: properties → cost → metrics → advisors → analysis."""
    if not enrichment_sync_enabled():
        return {"status": "disabled", "subscription_id": subscription_id.lower()}

    sub = subscription_id.strip().lower()
    stage_cfg = stages or SyncStages.from_env()
    snapshot = _resolve_snapshot(db, sub, resource_id, arm_id=arm_id)
    if not snapshot:
        return {
            "status": "not_found",
            "subscription_id": sub,
            "resource_id": resource_id or arm_id,
        }

    rid = normalize_arm_id(snapshot.resource_id)
    stage_results: dict[str, Any] = {"arm_id": rid}

    if snapshot.resource_type == "containers/aks" and token:
        try:
            from app.auth import arm_auth_context
            from app.azure_resources import AzureResourcesClient
            from app.db_sync import refresh_aks_cluster_snapshot

            with arm_auth_context(db=db, token=token):
                client = AzureResourcesClient(db=db)
                stage_results["aks_inventory"] = refresh_aks_cluster_snapshot(
                    db, client, sub, snapshot,
                )
        except Exception as exc:
            stage_results["aks_inventory"] = {
                "status": "error",
                "error": str(exc)[:300],
            }

    if stage_cfg.properties:
        stage_results["properties"] = _stage_properties(db, sub, snapshot)

    if stage_cfg.cost:
        try:
            stage_results["cost"] = _stage_cost(db, sub, snapshot)
        except Exception as exc:
            stage_results["cost"] = {"status": "error", "error": str(exc)[:300]}

    if stage_cfg.metrics:
        try:
            stage_results["metrics"] = _stage_metrics(db, sub, snapshot, token=token)
        except Exception as exc:
            stage_results["metrics"] = {"status": "error", "error": str(exc)[:300]}

    if stage_cfg.advisors:
        if token:
            try:
                from app.advisor_sync import sync_azure_advisor_recommendations

                sync_azure_advisor_recommendations(sub, db, token)
            except Exception as exc:
                stage_results["advisor_sync"] = {"status": "error", "error": str(exc)[:200]}
        try:
            stage_results["advisors"] = _stage_advisors(db, sub, snapshot, token=token)
        except Exception as exc:
            stage_results["advisors"] = {"status": "error", "error": str(exc)[:300]}

    if stage_cfg.analysis:
        try:
            stage_results["analysis"] = _stage_analysis(db, sub, snapshot)
        except Exception as exc:
            stage_results["analysis"] = {"status": "error", "error": str(exc)[:300]}

    db.commit()
    return {
        "status": "ok",
        "subscription_id": sub,
        "resource_id": rid,
        "stages": stage_results,
    }


def sync_subscription_full(
    db: Session,
    subscription_id: str,
    *,
    token: str | None = None,
    stages: SyncStages | None = None,
    arm_ids: set[str] | None = None,
    timeout_sec: int | None = None,
) -> dict[str, Any]:
    """Run enrichment for a subscription or scoped ARM ids (batch metrics/analysis where possible)."""
    if not enrichment_sync_enabled():
        return {"status": "disabled", "subscription_id": subscription_id.lower()}

    sub = subscription_id.strip().lower()
    stage_cfg = stages or SyncStages.from_env()
    timeout = timeout_sec if timeout_sec is not None else enrichment_timeout_sec()
    stage_results: dict[str, Any] = {}

    if stage_cfg.properties:
        count = sync_properties_for_subscription(db, sub, arm_ids=arm_ids)
        stage_results["properties"] = {"status": "ok", "count": count}

    if stage_cfg.cost:
        def _cost_batch() -> dict[str, Any]:
            count = sync_cost_for_subscription(db, sub)
            return {"status": "ok", "count": count}

        stage_results["cost"] = _run_with_timeout(_cost_batch, timeout_sec=timeout, stage="cost")

    if stage_cfg.metrics:
        def _metrics_batch() -> dict[str, Any]:
            if arm_ids and len(arm_ids) <= 25:
                ok = 0
                for rid in sorted(normalize_arm_id(r) for r in arm_ids):
                    snap = _resolve_snapshot(db, sub, rid)
                    if not snap:
                        continue
                    result = _stage_metrics(db, sub, snap, token=token)
                    if result.get("ok"):
                        ok += 1
                return {"status": "ok", "mode": "per_resource", "metrics_ok": ok, "total": len(arm_ids)}
            from app.workers.inventory_metrics_worker import run_inventory_metrics_worker

            return run_inventory_metrics_worker(db, sub, token=token)

        stage_results["metrics"] = _run_with_timeout(
            _metrics_batch,
            timeout_sec=timeout,
            stage="metrics",
        )

    if stage_cfg.advisors:
        if token:
            try:
                from app.advisor_sync import sync_azure_advisor_recommendations

                advisor_sync = sync_azure_advisor_recommendations(sub, db, token)
                stage_results["advisor_sync"] = {
                    "status": advisor_sync.get("status", "ok"),
                    "stored": advisor_sync.get("stored", 0),
                }
            except Exception as exc:
                stage_results["advisor_sync"] = {"status": "error", "error": str(exc)[:200]}

        def _advisor_batch() -> dict[str, Any]:
            count = sync_advisor_enrichment_for_subscription(db, sub, arm_ids=arm_ids)
            return {"status": "ok", "count": count}

        stage_results["advisors"] = _run_with_timeout(
            _advisor_batch,
            timeout_sec=timeout,
            stage="advisors",
        )

    if stage_cfg.analysis:
        def _analysis_batch() -> dict[str, Any]:
            from app.analysis import run_db_analysis

            scoped = sorted(normalize_arm_id(r) for r in arm_ids) if arm_ids else None
            if scoped:
                result = run_db_analysis(
                    db,
                    subscription_id=sub,
                    scope_resource_ids=scoped,
                    fetch_monitor_metrics=False,
                    include_ai=False,
                )
            else:
                result = run_db_analysis(
                    db,
                    subscription_id=sub,
                    fetch_monitor_metrics=False,
                    include_ai=False,
                )
            copied = sync_recommendations_from_snapshots(db, sub)
            return {
                "status": result.get("status", "ok"),
                "findings": result.get("findings_count") or result.get("total_findings"),
                "enrichment_rows": copied,
            }

        stage_results["analysis"] = _run_with_timeout(
            _analysis_batch,
            timeout_sec=timeout,
            stage="analysis",
        )

    db.commit()
    return {
        "status": "ok",
        "subscription_id": sub,
        "scoped_arm_ids": sorted(normalize_arm_id(r) for r in arm_ids) if arm_ids else None,
        "stages": stage_results,
    }


def _run_subscription_enrichment_background(
    subscription_id: str,
    token: str | None,
    arm_ids: set[str] | None,
) -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        result = sync_subscription_full(db, subscription_id, token=token, arm_ids=arm_ids)
        log.info(
            "subscription_enrichment_background.done",
            subscription_id=subscription_id.lower(),
            status=result.get("status"),
        )
    except Exception as exc:
        log.exception(
            "subscription_enrichment_background.failed",
            subscription_id=subscription_id.lower(),
            error=str(exc)[:300],
        )
    finally:
        db.close()


def queue_subscription_enrichment_after_sync(
    db: Session,
    subscription_id: str,
    *,
    token: str | None = None,
    arm_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Queue or run post-inventory enrichment without blocking the inventory sync commit."""
    if not enrichment_sync_enabled():
        return {"status": "disabled", "subscription_id": subscription_id.lower()}

    sub = subscription_id.strip().lower()
    if enrichment_async_enabled():
        threading.Thread(
            target=_run_subscription_enrichment_background,
            args=(sub, token, arm_ids),
            daemon=True,
            name=f"sync-enrich-{sub[:8]}",
        ).start()
        return {"status": "queued", "subscription_id": sub, "async": True}

    return sync_subscription_full(db, sub, token=token, arm_ids=arm_ids)
