"""Parallel ARM resource type fetching (1-F)."""

from __future__ import annotations

import contextvars
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

_SYNC_WORKERS = max(1, int(os.getenv("ARM_SYNC_WORKERS", "6")))


def parallel_fetch(
    specs: list[tuple[str, Callable[[], Any]]],
    *,
    max_workers: int | None = None,
) -> dict[str, Any]:
    """
    Run independent ARM list fetchers in parallel.
    specs: [(canonical_type, callable returning list)]
  """
    if not specs:
        return {}
    if len(specs) == 1:
        key, fn = specs[0]
        return {key: fn()}

    workers = min(max_workers or _SYNC_WORKERS, len(specs))
    results: dict[str, Any] = {}
    ctx = contextvars.copy_context()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(ctx.run, fn): key for key, fn in specs}
        for future in as_completed(futures):
            key = futures[future]
            results[key] = future.result()
    return results
