"""Platform cost service — mounts monolith cost routes."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

app = FastAPI(title="CostOptimizer Platform Cost", version="1.0.0")

from app.routers.costs import router as costs_router  # noqa: E402

app.include_router(costs_router)


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok", "service": "platform-cost"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8011")),
        reload=os.getenv("RELOAD", "") == "1",
    )
