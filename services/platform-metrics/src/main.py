"""Platform metrics service — Azure Monitor explorer and utilization APIs."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _scheduled_workers_enabled() -> bool:
    from app.scheduler_utils import env_bool

    return env_bool("SCHEDULED_OPERATIONS_ENABLED", False)


def _start_metrics_workers() -> None:
    from app.messaging.service_hooks import start_kafka_consumers_for_service

    start_kafka_consumers_for_service("platform-metrics")
    if not _scheduled_workers_enabled():
        return
    from app.metrics_sync_worker import metrics_sync_worker_enabled, start_metrics_sync_worker

    if metrics_sync_worker_enabled():
        start_metrics_sync_worker()


from app.platform_service import create_platform_service_app  # noqa: E402

app = create_platform_service_app(
    title="CostOptimizer Platform Metrics",
    service_id="platform-metrics",
    profile="metrics",
    on_startup=_start_metrics_workers,
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8014")),
        reload=os.getenv("RELOAD", "") == "1",
    )
