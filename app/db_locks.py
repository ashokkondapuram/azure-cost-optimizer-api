"""Shared PostgreSQL advisory lock helpers (extracted from operations_scheduler)."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

SCHEDULER_ADVISORY_LOCK_ID = 8247331
ENGINE_SCORING_ADVISORY_LOCK_ID = 8247332
PIPELINE_ADVISORY_LOCK_ID = 8247333


def _is_postgres(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def try_acquire_lock(db: Session, lock_id: int) -> bool:
    if _is_postgres(db):
        return bool(
            db.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": lock_id},
            ).scalar()
        )
    # SQLite / other dialects: always succeed (single-process)
    return True


def release_lock(db: Session, lock_id: int) -> None:
    if _is_postgres(db):
        db.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": lock_id},
        )
