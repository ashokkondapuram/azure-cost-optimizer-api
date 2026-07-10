"""Microservice for analytics/mlworkspace (Azure ML workspace)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from costoptimizer_core import create_resource_service, get_service_config

SERVICE_ID = "analytics-mlworkspace"
app = create_resource_service(get_service_config(SERVICE_ID))

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8103"))
    uvicorn.run(
        "service_app:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=port,
        reload=os.getenv("RELOAD", "") == "1",
    )
