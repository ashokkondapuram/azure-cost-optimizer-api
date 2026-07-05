"""Shared database / live Azure resolution for cost API endpoints."""

from __future__ import annotations

from typing import Any, Callable


def live_range_kw(range_kw: dict[str, Any]) -> dict[str, Any]:
    """Keyword args safe for live Cost Management queries (no DB-only filters)."""
    out: dict[str, Any] = {}
    if range_kw.get("timeframe"):
        out["timeframe"] = range_kw["timeframe"]
    if range_kw.get("from_date"):
        out["from_date"] = range_kw["from_date"]
    if range_kw.get("to_date"):
        out["to_date"] = range_kw["to_date"]
    return out


def resolve_cost_db_then_live(
    *,
    db_call: Callable[[], dict | None],
    live_call: Callable[[], dict | None],
) -> tuple[dict | None, str | None]:
    """Read synced database rows first; fall back to live Azure when empty."""
    db = db_call()
    if db:
        source = db.get("source") if isinstance(db.get("source"), str) else "database"
        return db, source or "database"
    live = live_call()
    if live:
        source = live.get("source") if isinstance(live.get("source"), str) else "azure"
        return live, source or "azure"
    return None, None
