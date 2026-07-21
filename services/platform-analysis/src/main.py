"""Platform analysis service — optimization engine, findings, and recommendations."""

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


def _start_operations_scheduler() -> None:
    from app.messaging.service_hooks import start_kafka_consumers_for_service

    start_kafka_consumers_for_service("platform-analysis")
    if not _scheduled_workers_enabled():
        return
    from app import operations_scheduler

    operations_scheduler.start()


from app.platform_service import create_platform_service_app  # noqa: E402

app = create_platform_service_app(
    title="CostOptimizer Platform Analysis",
    service_id="platform-analysis",
    profile="analysis",
    on_startup=_start_operations_scheduler,
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8013")),
        reload=os.getenv("RELOAD", "") == "1",
    )
