"""Shared helpers for building optimization analysis result payloads."""
from __future__ import annotations

from typing import Any


def _finding_evidence(finding: dict[str, Any]) -> dict[str, Any]:
    ev = finding.get("evidence")
    return ev if isinstance(ev, dict) else {}


def summarize_findings(
    findings: list[dict],
    engine_version: str,
    metrics_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build analysis summary payload from a flat findings list."""
    by_sev: dict[str, int] = {}
    by_cat: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    total_savings = 0.0
    retail_backed = 0
    full_monitor = 0
    for f in findings:
        by_sev[f["severity"]] = by_sev.get(f["severity"], 0) + 1
        by_cat[f["category"]] = by_cat.get(f["category"], 0) + 1
        pri = f.get("action_priority")
        if pri:
            by_priority[pri] = by_priority.get(pri, 0) + 1
        total_savings += f.get("estimated_savings_usd") or 0
        ev = _finding_evidence(f)
        if ev.get("pricing_status") == "available" or ev.get("pricing_source") == "azure_retail_prices":
            retail_backed += 1
        if ev.get("data_quality") == "full_monitor" or ev.get("monitor_facts_status") == "available":
            full_monitor += 1

    rule_totals: dict[str, dict] = {}
    for f in findings:
        rule_totals.setdefault(
            f["rule_id"],
            {"rule_id": f["rule_id"], "rule_name": f["rule_name"], "count": 0, "estimated_savings_usd": 0.0},
        )
        row = rule_totals[f["rule_id"]]
        row["count"] += 1
        row["estimated_savings_usd"] = round(row["estimated_savings_usd"] + (f.get("estimated_savings_usd") or 0), 2)

    top_rules = sorted(rule_totals.values(), key=lambda r: (-r["estimated_savings_usd"], -r["count"]))[:5]
    conf = [f.get("confidence_score") or 0 for f in findings]
    total = len(findings) or 1

    summary: dict[str, Any] = {
        "total_findings": len(findings),
        "total_estimated_monthly_savings_usd": round(total_savings, 2),
        "total_estimated_annual_savings_usd": round(total_savings * 12, 2),
        "by_severity": by_sev,
        "by_category": by_cat,
        "by_priority": by_priority,
        "top_rules": top_rules,
        "average_confidence_score": round(sum(conf) / len(conf), 1) if conf else 0,
        "findings_with_retail_pricing": retail_backed,
        "findings_with_full_monitor": full_monitor,
        "retail_pricing_pct": round(100.0 * retail_backed / total, 1),
        "full_monitor_pct": round(100.0 * full_monitor / total, 1),
    }
    if metrics_context:
        summary["metrics_context"] = metrics_context

    return {
        "summary": summary,
        "findings": findings,
        "engine_version": engine_version,
    }


def merge_analysis_results(
    partials: list[dict[str, Any]],
    engine_version: str,
    metrics_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combine batched partial engine outputs into one result payload."""
    findings: list[dict] = []
    for partial in partials:
        findings.extend(partial.get("findings") or [])
    return summarize_findings(findings, engine_version, metrics_context=metrics_context)
