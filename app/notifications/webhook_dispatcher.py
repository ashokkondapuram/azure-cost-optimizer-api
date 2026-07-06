"""Webhook Dispatcher

Fires outbound webhook notifications for any alert payload.
Supports Slack (blocks), Microsoft Teams (Adaptive Cards), and generic JSON.
All dispatches are fire-and-forget (async, non-blocking).

Configuration via environment variables:
  WEBHOOK_URL         — target URL
  WEBHOOK_TYPE        — slack | teams | generic  (default: generic)
  WEBHOOK_SECRET      — HMAC-SHA256 signing secret (optional)
  WEBHOOK_TIMEOUT_SEC — per-request timeout in seconds (default: 10)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
_WEBHOOK_TYPE = os.getenv("WEBHOOK_TYPE", "generic").lower()
_WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
_WEBHOOK_TIMEOUT = int(os.getenv("WEBHOOK_TIMEOUT_SEC", "10"))


def _slack_blocks(payload: dict[str, Any]) -> dict[str, Any]:
    severity_emoji = {"critical": "❌", "warning": "⚠️", "info": "ℹ️"}.get(
        payload.get("severity", "info"), "🔔"
    )
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{severity_emoji} {payload.get('summary', 'Alert')}",
            },
        },
        {"type": "divider"},
    ]
    for line in (payload.get("details") or [])[:10]:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": line},
        })
    return {"blocks": blocks}


def _teams_card(payload: dict[str, Any]) -> dict[str, Any]:
    color_map = {"critical": "attention", "warning": "warning", "info": "good"}
    color = color_map.get(payload.get("severity", "info"), "default")
    facts = [
        {"title": "Subscription", "value": payload.get("subscription_id", "N/A")},
        {"title": "Severity", "value": payload.get("severity", "info").upper()},
        {"title": "Type", "value": payload.get("type", "alert")},
    ]
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.4",
                "msteams": {"width": "Full"},
                "body": [
                    {
                        "type": "TextBlock",
                        "text": payload.get("summary", "Alert"),
                        "weight": "Bolder",
                        "size": "Medium",
                        "color": color,
                    },
                    {
                        "type": "FactSet",
                        "facts": facts,
                    },
                ] + [
                    {"type": "TextBlock", "text": line, "wrap": True}
                    for line in (payload.get("details") or [])[:8]
                ],
            },
        }],
    }


def _sign(body: bytes) -> str | None:
    if not _WEBHOOK_SECRET:
        return None
    sig = hmac.new(_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


async def dispatch_webhook(payload: dict[str, Any], url: str | None = None) -> bool:
    """Dispatch a webhook notification asynchronously.

    Returns True if the request succeeded (2xx), False otherwise.
    Never raises — all exceptions are swallowed and logged.
    """
    target = url or _WEBHOOK_URL
    if not target:
        log.debug("webhook_dispatcher.no_url_configured")
        return False

    if _WEBHOOK_TYPE == "slack":
        body_dict = _slack_blocks(payload)
    elif _WEBHOOK_TYPE == "teams":
        body_dict = _teams_card(payload)
    else:
        body_dict = payload

    body_bytes = json.dumps(body_dict).encode()
    headers = {"Content-Type": "application/json"}
    sig = _sign(body_bytes)
    if sig:
        headers["X-Hub-Signature-256"] = sig

    try:
        import httpx
        async with httpx.AsyncClient(timeout=_WEBHOOK_TIMEOUT) as client:
            resp = await client.post(target, content=body_bytes, headers=headers)
            ok = resp.status_code < 300
            log.info(
                "webhook_dispatcher.sent",
                url=target,
                status=resp.status_code,
                ok=ok,
            )
            return ok
    except Exception as exc:
        log.warning("webhook_dispatcher.failed", url=target, error=str(exc))
        return False
