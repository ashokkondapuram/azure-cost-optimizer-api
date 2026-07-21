"""In-process pub/sub for sync pipeline SSE progress events."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any

_subscribers: dict[str, list[asyncio.Queue[str]]] = defaultdict(list)
_global_subscribers: list[asyncio.Queue[str]] = []


def _subscription_key(subscription_id: str | None) -> str:
    return (subscription_id or "").strip().lower()


def publish_sync_progress_event(
    payload: dict[str, Any],
    *,
    subscription_id: str | None = None,
    broadcast_all: bool = False,
) -> None:
    """Broadcast a sync progress event to SSE subscribers."""
    message = json.dumps(payload, default=str)
    dead: list[asyncio.Queue[str]] = []

    if broadcast_all:
        for queue in list(_global_subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                dead.append(queue)
        for queue in dead:
            try:
                _global_subscribers.remove(queue)
            except ValueError:
                pass
        dead.clear()

    sub = _subscription_key(subscription_id)
    if not sub:
        return

    for queue in list(_subscribers.get(sub, [])):
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            dead.append(queue)
    for queue in dead:
        try:
            _subscribers[sub].remove(queue)
        except ValueError:
            pass


async def subscribe_sync_progress_events(
    subscription_id: str | None = None,
    *,
    all_subscriptions: bool = False,
):
    """Async generator yielding SSE data lines for sync progress."""
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
    sub = _subscription_key(subscription_id)

    if all_subscriptions:
        _global_subscribers.append(queue)
    elif sub:
        _subscribers[sub].append(queue)
    else:
        _global_subscribers.append(queue)

    try:
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=25.0)
                yield f"data: {payload}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    finally:
        if all_subscriptions or not sub:
            try:
                _global_subscribers.remove(queue)
            except ValueError:
                pass
        if sub:
            try:
                _subscribers[sub].remove(queue)
            except ValueError:
                pass
