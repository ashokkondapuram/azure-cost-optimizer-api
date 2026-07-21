"""Azure Cost Management client that routes queries through Kafka API workers."""

from __future__ import annotations

from typing import Any

import structlog

from app.messaging.api_throttle.config import kafka_api_throttle_enabled
from app.messaging.api_throttle.coordinator import enqueue_single_cost_phase

log = structlog.get_logger(__name__)

_PHASE_BY_OPERATION = {
    "query_subscription_totals": "subscription_totals",
    "query_cost_by_service": "cost_by_service",
    "query_cost_mtd_by_resource_type": "cost_by_resource_type",
    "query_cost_daily_subscription": "daily_subscription",
    "query_cost_by_resource": "cost_by_resource",
}


class KafkaThrottledAzureCostClient:
    """Drop-in replacement for AzureCostClient when Kafka throttling is enabled."""

    def __init__(
        self,
        *,
        subscription_id: str,
        pipeline_id: str,
        token: str | None = None,
        db=None,
        source_service: str = "platform-cost",
    ):
        self._subscription_id = subscription_id.lower()
        self._pipeline_id = pipeline_id or f"cost-sync:{subscription_id}"
        self._token = token
        self._db = db
        self._source_service = source_service
        self._run_params = {"token": token} if token else {}

    def _enqueue(self, operation: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        phase = _PHASE_BY_OPERATION.get(operation)
        if phase is None:
            raise ValueError(f"Unknown cost operation: {operation}")
        if phase.startswith("period_total_"):
            pass
        return enqueue_single_cost_phase(
            subscription_id=self._subscription_id,
            pipeline_id=self._pipeline_id,
            phase=phase,
            api_params=dict(params or {}),
            run_params=self._run_params,
            source_service=self._source_service,
        )

    def query_subscription_totals(
        self,
        subscription_id: str,
        timeframe: str = "MonthToDate",
        *,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict:
        if from_date and to_date:
            return self._enqueue(
                "query_subscription_totals",
                params={"timeframe": timeframe, "from_date": from_date, "to_date": to_date},
            )
        return self._enqueue("query_subscription_totals", params={"timeframe": timeframe})

    def query_cost_by_service(
        self,
        subscription_id: str,
        timeframe: str = "MonthToDate",
        *,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict:
        return self._enqueue(
            "query_cost_by_service",
            params={"timeframe": timeframe, "from_date": from_date, "to_date": to_date},
        )

    def query_cost_mtd_by_resource_type(
        self,
        subscription_id: str,
        timeframe: str = "MonthToDate",
    ) -> dict:
        return self._enqueue("query_cost_mtd_by_resource_type", params={"timeframe": timeframe})

    def query_cost_daily_subscription(
        self,
        subscription_id: str,
        timeframe: str = "MonthToDate",
        *,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict:
        return self._enqueue(
            "query_cost_daily_subscription",
            params={"timeframe": timeframe, "from_date": from_date, "to_date": to_date},
        )

    def query_cost_by_resource(
        self,
        subscription_id: str,
        timeframe: str = "MonthToDate",
        *,
        resource_groups: list[str] | None = None,
    ) -> dict:
        return self._enqueue(
            "query_cost_by_resource",
            params={"timeframe": timeframe, "resource_groups": resource_groups},
        )


def cost_client_for_sync(
    *,
    subscription_id: str,
    pipeline_id: str,
    db=None,
    token: str | None = None,
):
    """Return Kafka-throttled or inline AzureCostClient based on config."""
    if kafka_api_throttle_enabled():
        log.info(
            "api_throttle.cost_client_kafka",
            subscription_id=subscription_id,
            pipeline_id=pipeline_id,
        )
        return KafkaThrottledAzureCostClient(
            subscription_id=subscription_id,
            pipeline_id=pipeline_id,
            token=token,
            db=db,
        )

    from app.azure_cost import AzureCostClient

    return AzureCostClient(db=db, token=token)
