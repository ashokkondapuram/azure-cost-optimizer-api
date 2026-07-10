"""Shared pagination helpers for list endpoints."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 50
DEFAULT_MIN_LIMIT = 1
DEFAULT_MAX_LIMIT = 200


@dataclass(frozen=True)
class PaginationParams:
    limit: int
    offset: int
    cursor: str | None = None


def validate_pagination(
    limit: int | None,
    offset: int = 0,
    *,
    cursor: str | None = None,
    min_limit: int = DEFAULT_MIN_LIMIT,
    max_limit: int = DEFAULT_MAX_LIMIT,
    default_limit: int = DEFAULT_PAGE_SIZE,
) -> PaginationParams:
    """Normalize limit/offset/cursor for inventory list endpoints."""
    resolved = min(max(min_limit, int(limit or default_limit)), max_limit)
    resolved_offset = max(0, int(offset or 0))
    cursor_text = (cursor or "").strip() or None
    return PaginationParams(limit=resolved, offset=resolved_offset, cursor=cursor_text)


def encode_cursor(resource_name: str, resource_id: str) -> str:
    payload = f"{resource_name or ''}\x1f{resource_id or ''}"
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> tuple[str, str] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
        name, _, rid = raw.partition("\x1f")
        if rid:
            return name, rid
    except Exception:
        return None
    return None


def slice_page(rows: list[T], limit: int) -> tuple[list[T], bool, int]:
    """
    Apply the LIMIT+1 pattern.

    Returns (items, has_more, page_count) where page_count is the number of DB rows
    consumed before trimming the probe row.
    """
    limit = max(1, int(limit))
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    return page_rows, has_more, len(page_rows)


def cached_total(key: str, loader: Callable[[], int], *, cache_fn: Callable[[str, Callable[[], Any]], Any]) -> int:
    """TTL-cached total row count for paginated list footers."""
    return int(cache_fn(key, loader) or 0)


def page_envelope(
    items: list,
    *,
    total: int,
    limit: int,
    offset: int,
    has_more: bool,
    page_count: int,
    next_cursor: str | None = None,
    recommended_page_size: int = DEFAULT_PAGE_SIZE,
    max_page_size: int = DEFAULT_MAX_LIMIT,
) -> dict:
    """Standard paginated list response envelope."""
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "page_count": page_count,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "recommended_page_size": recommended_page_size,
        "max_page_size": max_page_size,
    }
