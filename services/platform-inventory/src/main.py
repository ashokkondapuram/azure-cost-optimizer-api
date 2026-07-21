"""Platform inventory service — Azure Resource Graph sync and resource listings."""

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


def _start_inventory_workers() -> None:
    from app.messaging.service_hooks import start_kafka_consumers_for_service

    start_kafka_consumers_for_service("platform-inventory")
    if not _scheduled_workers_enabled():
        return
    from app.resource_discovery_worker import resource_discovery_worker_enabled, start

    if resource_discovery_worker_enabled():
        start()


from app.platform_service import create_platform_service_app  # noqa: E402

app = create_platform_service_app(
    title="CostOptimizer Platform Inventory",
    service_id="platform-inventory",
    profile="inventory",
    on_startup=_start_inventory_workers,
)

from app.azure_live_api import register_azure_live_routes  # noqa: E402
from app.azure_resources import AzureResourcesClient  # noqa: E402
from app.user_auth import require_admin_user  # noqa: E402

register_azure_live_routes(app, AzureResourcesClient(), require_admin_user=require_admin_user)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8012")),
        reload=os.getenv("RELOAD", "") == "1",
    )
