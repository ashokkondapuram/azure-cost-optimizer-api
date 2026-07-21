"""Execute individual Cost Management API phases."""

from __future__ import annotations

from typing import Any

import structlog

from app.messaging.api_throttle.envelope import ApiDomain
from app.messaging.api_throttle.rate_limiter import get_rate_limiter

log = structlog.get_logger(__name__)


def execute_cost_phase(
    *,
    subscription_id: str,
    phase: str,
    api_params: dict[str, Any],
    token: str,
) -> dict[str, Any]:
    """Run one Cost Management query with rate limiting."""
    from app.auth import arm_auth_context
    from app.azure_cost import AzureCostClient
    from app.database import SessionLocal
    from app.messaging.api_throttle import metrics as throttle_metrics

    limiter = get_rate_limiter(ApiDomain.COST_MANAGEMENT)
    limiter.acquire(label=phase)
    db = SessionLocal()
    try:
        with arm_auth_context(db=db, token=token):
            client = AzureCostClient(db=db, token=token)
            return _dispatch_cost_phase(client, subscription_id, phase, api_params)
    except Exception as exc:
        text = str(exc)
        if "429" in text or "TooManyRequests" in text:
            limiter.record_429()
            throttle_metrics.get_metrics().record_429(api_kind="cost", phase=phase)
        raise
    finally:
        db.close()


def _dispatch_cost_phase(
    client,
    subscription_id: str,
    phase: str,
    api_params: dict[str, Any],
) -> dict[str, Any]:
    if phase == "subscription_totals":
        return client.query_subscription_totals(subscription_id)
    if phase == "cost_by_service":
        return client.query_cost_by_service(subscription_id)
    if phase == "cost_by_resource_type":
        return client.query_cost_mtd_by_resource_type(subscription_id)
    if phase == "daily_subscription":
        return client.query_cost_daily_subscription(
            subscription_id,
            timeframe=api_params.get("timeframe", "Custom"),
            from_date=api_params.get("from_date"),
            to_date=api_params.get("to_date"),
        )
    if phase == "cost_by_resource":
        return client.query_cost_by_resource(subscription_id)
    if phase.startswith("period_total_"):
        period_tf = api_params.get("period_timeframe") or phase.removeprefix("period_total_")
        return client.query_subscription_totals(
            subscription_id,
            timeframe=api_params.get("timeframe", "MonthToDate"),
            **(
                {
                    "from_date": api_params["from_date"],
                    "to_date": api_params["to_date"],
                }
                if api_params.get("from_date") and api_params.get("to_date")
                else {}
            ),
        )
    raise ValueError(f"Unknown cost API phase: {phase}")
