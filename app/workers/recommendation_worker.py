"""Recommendation worker — unified assessment rules + legacy sub-engines."""

from __future__ import annotations

import os
import structlog
from sqlalchemy.orm import Session
from typing import Any

from app.pipeline.unified_recommendations import run_unified_recommendations

log = structlog.get_logger(__name__)


def recommendation_worker_enabled() -> bool:
    return os.getenv("RECOMMENDATION_WORKER_ENABLED", "true").lower() not in {"0", "false", "no"}


def run_recommendation_worker(db: Session, subscription_id: str) -> dict[str, Any]:
    """Run the unified recommendation engine for one subscription."""
    sub = subscription_id.lower()
    if not recommendation_worker_enabled():
        return {
            "subscription_id": sub,
            "status": "disabled",
            "findings": 0,
        }
    return run_unified_recommendations(db, sub)
