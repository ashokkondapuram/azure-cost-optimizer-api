"""Platform orchestrator — fans out analysis to migrated resource services."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "costoptimizer-core"))

from costoptimizer_core.registry import MIGRATED_SERVICES, all_service_configs, get_service_config

MONOLITH_URL = os.getenv("MONOLITH_URL", "http://127.0.0.1:8000").rstrip("/")

app = FastAPI(title="CostOptimizer Platform Orchestrator", version="1.0.0")


class AnalyzeFanoutRequest(BaseModel):
    subscription_id: str
    profile: str = "default"
    engine_version: str = "extended"
    service_ids: list[str] = Field(default_factory=list)


class AnalyzeFanoutResponse(BaseModel):
    subscription_id: str
    migrated_results: list[dict[str, Any]] = Field(default_factory=list)
    monolith_result: dict[str, Any] | None = None


def _db_dep():
    from app.database import get_db

    yield from get_db()


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok", "service": "platform-orchestrator"}


async def _analyze_service(client: httpx.AsyncClient, service_id: str, body: dict[str, Any]) -> dict[str, Any]:
    cfg = get_service_config(service_id)
    url = f"{cfg.base_url.rstrip('/')}/v1/analyze"
    res = await client.post(url, json=body, timeout=300.0)
    res.raise_for_status()
    data = res.json()
    return {"service_id": service_id, "canonical_type": cfg.canonical_type, "result": data}


@app.post("/v1/analyze/fanout", response_model=AnalyzeFanoutResponse)
async def analyze_fanout(body: AnalyzeFanoutRequest) -> AnalyzeFanoutResponse:
    sub = body.subscription_id.strip().lower()
    payload = {
        "subscription_id": sub,
        "profile": body.profile,
        "engine_version": body.engine_version,
    }
    targets = body.service_ids or sorted(MIGRATED_SERVICES)
    migrated_results: list[dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        tasks = [_analyze_service(client, sid, payload) for sid in targets if sid in MIGRATED_SERVICES]
        if tasks:
            migrated_results = list(await asyncio.gather(*tasks, return_exceptions=False))

    monolith_result = None
    unmigrated = [
        c for c in all_service_configs()
        if c.service_id not in MIGRATED_SERVICES and (not body.service_ids or c.service_id in body.service_ids)
    ]
    if unmigrated:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{MONOLITH_URL}/optimize/analyze",
                json={
                    "subscription_id": sub,
                    "profile": body.profile,
                    "engine_version": body.engine_version,
                },
                timeout=600.0,
            )
            if res.status_code < 400:
                monolith_result = res.json()

    return AnalyzeFanoutResponse(
        subscription_id=sub,
        migrated_results=migrated_results,
        monolith_result=monolith_result,
    )


@app.post("/optimize/analyze")
def analyze_monolith_compat(body: AnalyzeFanoutRequest, db: Session = Depends(_db_dep)):
    """Compatibility shim — run full DB analysis via monolith logic."""
    from app.db_analyze import run_db_analysis

    sub = body.subscription_id.strip().lower()
    try:
        return run_db_analysis(
            db,
            subscription_id=sub,
            profile=body.profile,
            engine_version=body.engine_version,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8012")),
        reload=os.getenv("RELOAD", "") == "1",
    )
