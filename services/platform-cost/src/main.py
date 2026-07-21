"""Platform cost service — cost sync, explorer API, billing, and retail pricing."""

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


def _start_cost_scheduler() -> None:
    from app.messaging.service_hooks import start_kafka_consumers_for_service

    start_kafka_consumers_for_service("platform-cost")
    if not _scheduled_workers_enabled():
        return
    from app.cost_explorer_worker import cost_explorer_worker_enabled, start

    if cost_explorer_worker_enabled():
        start()


from app.platform_service import create_platform_service_app  # noqa: E402

app = create_platform_service_app(
    title="CostOptimizer Platform Cost",
    service_id="platform-cost",
    profile="cost",
    on_startup=_start_cost_scheduler,
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8011")),
        reload=os.getenv("RELOAD", "") == "1",
    )
