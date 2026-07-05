"""POST finding summaries to Slack, Teams, or arbitrary webhook URLs.

Usage::

    from app.notifications.webhook_dispatcher import dispatch_findings_summary
    dispatch_findings_summary(findings, webhook_url="https://hooks.slack.com/...")
"""
from __future__ import annotations

import json
import threading
from typing import Any

import requests
import structlog

log = structlog.get_logger(__name__)

_DEFAULT_TIMEOUT = 10


def _slack_payload(summary: dict[str, Any]) -> dict[str, Any]:
    total = summary.get("total_findings", 0)
    savings = summary.get("total_savings_usd", 0.0)
    top = summary.get("top_findings") or []
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*:bar_chart: Azure Cost Optimizer — Analysis Complete*\n"
                    f"{total} finding(s) | Potential savings: *${savings:,.2f}/mo*"
                ),
            },
        }
    ]
    for f in top[:5]:
        name = f.get("resource_name") or "unknown"
        rule = f.get("rule_id") or ""
        s = float(f.get("estimated_savings_usd") or 0)
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"• `{name}` ({rule}) — ${s:,.2f}/mo"},
        })
    return {"blocks": blocks}


def _teams_payload(summary: dict[str, Any]) -> dict[str, Any]:
    total = summary.get("total_findings", 0)
    savings = summary.get("total_savings_usd", 0.0)
    return {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0076D7",
        "summary": "Azure Cost Optimizer Analysis",
        "sections": [
            {
                "activityTitle": "Azure Cost Optimizer — Analysis Complete",
                "facts": [
                    {"name": "Findings", "value": str(total)},
                    {"name": "Potential Savings", "value": f"${savings:,.2f}/mo"},
                ],
                "markdown": True,
            }
        ],
    }


def _build_payload(summary: dict[str, Any], webhook_url: str, fmt: str | None) -> dict[str, Any]:
    if fmt == "slack" or "hooks.slack.com" in webhook_url:
        return _slack_payload(summary)
    if fmt == "teams" or "webhook.office.com" in webhook_url or "outlook.office.com" in webhook_url:
        return _teams_payload(summary)
    # Generic JSON payload
    return {"azure_cost_optimizer": summary}


def build_findings_summary(findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Collapse a findings list into a compact summary dict."""
    total_savings = sum(float(f.get("estimated_savings_usd") or 0) for f in findings)
    top = sorted(findings, key=lambda f: float(f.get("estimated_savings_usd") or 0), reverse=True)[:5]
    return {
        "total_findings": len(findings),
        "total_savings_usd": round(total_savings, 2),
        "top_findings": [
            {
                "resource_name": f.get("resource_name"),
                "rule_id": f.get("rule_id"),
                "estimated_savings_usd": f.get("estimated_savings_usd"),
                "severity": f.get("severity"),
            }
            for f in top
        ],
    }


def dispatch_findings_summary(
    findings: list[dict[str, Any]],
    webhook_url: str,
    *,
    fmt: str | None = None,
    timeout: int = _DEFAULT_TIMEOUT,
    async_send: bool = True,
) -> None:
    """Send an analysis summary to a webhook URL.

    Args:
        findings: Full findings list from analysis result.
        webhook_url: Target URL (Slack incoming-webhook, Teams connector, or custom).
        fmt: Force payload format — ``'slack'``, ``'teams'``, or ``None`` (auto-detect).
        timeout: HTTP timeout in seconds.
        async_send: When True (default), fire-and-forget in a daemon thread.
    """
    summary = build_findings_summary(findings)
    payload = _build_payload(summary, webhook_url, fmt)

    def _send() -> None:
        try:
            resp = requests.post(
                webhook_url,
                json=payload,
                timeout=timeout,
                headers={"Content-Type": "application/json"},
            )
            if not resp.ok:
                log.warning(
                    "webhook.dispatch_failed",
                    status=resp.status_code,
                    body=resp.text[:300],
                )
            else:
                log.info("webhook.dispatch_ok", status=resp.status_code, url=webhook_url)
        except Exception as exc:
            log.warning("webhook.dispatch_error", error=str(exc))

    if async_send:
        threading.Thread(target=_send, daemon=True, name="webhook-dispatch").start()
    else:
        _send()


def dispatch_to_multiple(
    findings: list[dict[str, Any]],
    webhook_urls: list[str],
    **kwargs: Any,
) -> None:
    """Dispatch to multiple webhook endpoints in parallel daemon threads."""
    for url in webhook_urls:
        dispatch_findings_summary(findings, url, **kwargs)
