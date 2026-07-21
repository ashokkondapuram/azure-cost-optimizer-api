"""Azure Advisor REST client (Microsoft.Advisor recommendations)."""
from __future__ import annotations

import time
from typing import Any

import structlog

from app.http_client import BASE, AzureAPIError, _get_http_client, _raise_for, get_all_pages
from app.http_client import _bucket, _slots, _wait_for_global_cooldown

log = structlog.get_logger()

ADVISOR_API_VERSION = "2023-01-01"
GENERATE_POLL_SECONDS = 5
GENERATE_MAX_WAIT_SECONDS = 300


class AdvisorClient:
    """List and generate Azure Advisor recommendations for a subscription."""

    def __init__(self, headers: dict[str, str]):
        self._headers = headers

    def _post(self, url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        """POST that tolerates empty 202/204 Advisor generate responses."""
        _wait_for_global_cooldown()
        _bucket.acquire()
        with _slots:
            resp = _get_http_client().post(
                url, headers=self._headers, params=params, json={},
            )
        if resp.status_code in {429, 500, 502, 503, 504}:
            raise AzureAPIError(resp.status_code, "Retryable", resp.text[:200])
        _raise_for(resp)
        if resp.status_code in {200, 202, 204} and not resp.content:
            return {"status": "accepted"}
        try:
            return resp.json()
        except Exception:
            return {"status": "accepted"}

    def list_recommendations(
        self,
        subscription_id: str,
        *,
        category: str | None = None,
        use_cache: bool = False,
    ) -> list[dict[str, Any]]:
        sub = subscription_id.strip().lower()
        url = (
            f"{BASE}/subscriptions/{sub}/providers/Microsoft.Advisor/recommendations"
        )
        params: dict[str, str] = {"api-version": ADVISOR_API_VERSION}
        if category:
            params["$filter"] = f"Category eq '{category}'"
        return get_all_pages(url, self._headers, params, use_cache=use_cache)

    def generate_recommendations(self, subscription_id: str) -> dict[str, Any]:
        sub = subscription_id.strip().lower()
        url = (
            f"{BASE}/subscriptions/{sub}/providers/Microsoft.Advisor/"
            "recommendations/generate"
        )
        params = {"api-version": ADVISOR_API_VERSION}
        try:
            return self._post(url, params)
        except AzureAPIError:
            raise
        except Exception as exc:
            log.warning("advisor_generate_fallback", error=str(exc)[:120])
            return {"status": "accepted"}

    def generate_and_wait(
        self,
        subscription_id: str,
        *,
        max_wait_seconds: int = GENERATE_MAX_WAIT_SECONDS,
        poll_seconds: int = GENERATE_POLL_SECONDS,
    ) -> dict[str, Any]:
        """Trigger generate and poll list until recommendations refresh or timeout."""
        result = self.generate_recommendations(subscription_id)
        deadline = time.monotonic() + max(0, max_wait_seconds)
        before_count = len(self.list_recommendations(subscription_id, use_cache=False))
        while time.monotonic() < deadline:
            time.sleep(poll_seconds)
            after = self.list_recommendations(subscription_id, use_cache=False)
            if len(after) != before_count:
                return {
                    **result,
                    "status": "completed",
                    "recommendation_count": len(after),
                }
        return {
            **result,
            "status": "timeout",
            "recommendation_count": before_count,
            "message": "Generation started; recommendations may still be updating.",
        }
