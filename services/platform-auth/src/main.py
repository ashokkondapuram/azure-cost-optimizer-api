"""Platform auth service — mounts monolith auth routes."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

app = FastAPI(title="CostOptimizer Platform Auth", version="1.0.0")

from app.routers.auth import router as auth_router  # noqa: E402

app.include_router(auth_router)


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok", "service": "platform-auth"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8010")),
        reload=os.getenv("RELOAD", "") == "1",
    )
