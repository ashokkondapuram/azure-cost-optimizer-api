"""HTTP utilities for inter-service calls."""

from __future__ import annotations

from typing import Any

import httpx


def service_client(*, timeout: float = 120.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True)


async def proxy_request(
    client: httpx.AsyncClient,
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    content: bytes | None = None,
) -> httpx.Response:
    return await client.request(method, url, headers=headers, params=params, content=content)
