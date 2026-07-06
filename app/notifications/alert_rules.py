"""User-defined alert rules engine.

Evaluates a list of alert rules against incoming findings and triggers
webhook / email notifications when thresholds are exceeded.

Example rule (stored as JSON in the DB or config):

    {
        "rule_name": "high-savings-alert",
        "condition": "savings_usd_gte",
        "threshold": 500,
        "webhook_url": "https://hooks.slack.com/...",
        "severity_filter": ["critical", "high"],
        "enabled": true
    }
"""
from __future__ import annotations

from typing import Any

import structlog

from app.notifications.webhook_dispatcher import dispatch_findings_summary

log = structlog.get_logger(__name__)

SUPPORTED_CONDITIONS = {
    "savings_usd_gte",      # trigger when any single finding >= threshold
    "total_savings_gte",   # trigger when sum of all findings >= threshold
    "finding_count_gte",   # trigger when number of findings >= threshold
    "severity_contains",   # trigger when any finding has given severity
}


def _matches_severity_filter(finding: dict[str, Any], severity_filter: list[str]) -> bool:
    if not severity_filter:
        return True
    return str(finding.get("severity") or "").lower() in {s.lower() for s in severity_filter}


def evaluate_rule(rule: dict[str, Any], findings: list[dict[str, Any]]) -> bool:
    """Return True if the rule condition is met by the findings."""
    if not rule.get("enabled", True):
        return False

    condition = str(rule.get("condition") or "").strip().lower()
    threshold = rule.get("threshold", 0)
    severity_filter: list[str] = rule.get("severity_filter") or []

    filtered = [f for f in findings if _matches_severity_filter(f, severity_filter)]

    if condition == "savings_usd_gte":
        return any(float(f.get("estimated_savings_usd") or 0) >= float(threshold) for f in filtered)

    if condition == "total_savings_gte":
        total = sum(float(f.get("estimated_savings_usd") or 0) for f in filtered)
        return total >= float(threshold)

    if condition == "finding_count_gte":
        return len(filtered) >= int(threshold)

    if condition == "severity_contains":
        target = str(threshold).lower()
        return any(str(f.get("severity") or "").lower() == target for f in filtered)

    log.warning("alert_rules.unknown_condition", condition=condition)
    return False


def process_alert_rules(
    findings: list[dict[str, Any]],
    rules: list[dict[str, Any]],
) -> list[str]:
    """Evaluate all rules and dispatch notifications for those that match.

    Returns the list of rule names that fired.
    """
    fired: list[str] = []
    for rule in rules:
        rule_name = rule.get("rule_name") or "unnamed"
        try:
            if not evaluate_rule(rule, findings):
                continue
            log.info("alert_rules.fired", rule=rule_name)
            fired.append(rule_name)

            webhook_url = (rule.get("webhook_url") or "").strip()
            if webhook_url:
                dispatch_findings_summary(
                    findings,
                    webhook_url,
                    fmt=rule.get("webhook_format"),
                    async_send=True,
                )
        except Exception as exc:
            log.error("alert_rules.error", rule=rule_name, error=str(exc))
    return fired
