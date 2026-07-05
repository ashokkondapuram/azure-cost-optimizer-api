"""In-process pub/sub for analysis job SSE events."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any

_subscribers: dict[str, list[asyncio.Queue[str]]] = defaultdict(list)


def publish_job_event(subscription_id: str, payload: dict[str, Any]) -> None:
    """Broadcast a job event to all SSE subscribers for a subscription."""
    sub = (subscription_id or "").strip().lower()
    if not sub:
        return
    message = json.dumps(payload, default=str)
    dead: list[asyncio.Queue[str]] = []
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


async def subscribe_job_events(subscription_id: str):
    """Async generator yielding SSE data lines for one subscription."""
    sub = (subscription_id or "").strip().lower()
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
    _subscribers[sub].append(queue)
    try:
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=25.0)
                yield f"data: {payload}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    finally:
        try:
            _subscribers[sub].remove(queue)
        except ValueError:
            pass
