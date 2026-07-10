"""Post-analysis rule passes shared by standard and extended engines."""

from __future__ import annotations

from typing import Any

import structlog

from app.optimizer.database_advanced_rules import analyze_database_advanced
from app.optimizer.engine_runtime import filter_resources, passes_savings_gate
from app.optimizer.governance_rules import analyze_governance
from app.optimizer.network_advanced_rules import analyze_network_advanced
from app.optimizer.serverless_rules import analyze_serverless
from app.optimizer.standard_finding import Finding, extract_subscription_id

log = structlog.get_logger(__name__)


def network_resources_by_type(buckets: dict[str, list]) -> dict[str, list[dict]]:
    front = list(buckets.get("front_doors") or [])
    cdn = list(buckets.get("cdn_profiles") or [])
    return {
        "network/publicip": list(buckets.get("public_ips") or []),
        "network/trafficmanager": list(buckets.get("traffic_managers") or []),
        "network/frontdoor": front + [
            r for r in cdn
            if "frontdoor" in str(r.get("type") or "").lower()
            or "frontdoors" in str(r.get("id") or "").lower()
        ],
        "network/expressroute": list(buckets.get("expressroute_circuits") or []),
    }


def collect_governance_resources(buckets: dict[str, list]) -> list[dict]:
    keys = (
        "vms", "disks", "storage", "app_services", "sql_databases",
        "public_ips", "load_balancers", "aks_clusters",
    )
    out: list[dict] = []
    for key in keys:
        out.extend(buckets.get(key) or [])
    return out


def run_post_analysis(
    engine,
    *,
    buckets: dict[str, list],
    cost_by_resource: dict[str, float] | None,
    subscription_id: str | None = None,
) -> list[Finding]:
    sub_id = subscription_id or extract_subscription_id(
        ((buckets.get("vms") or [{}])[0]).get("id", ""),
    )
    costs = cost_by_resource or {}
    findings: list[Finding] = []
    try:
        findings.extend(analyze_database_advanced(engine, sub_id, buckets.get("sql_databases") or [], costs))
        findings.extend(analyze_network_advanced(engine, sub_id, network_resources_by_type(buckets), costs))
        resources = filter_resources(collect_governance_resources(buckets), getattr(engine, "global_config", None))
        findings.extend(analyze_governance(engine, sub_id, resources))
        findings.extend(analyze_serverless(engine, sub_id, buckets.get("app_services") or [], costs))
    except Exception as exc:
        log.error("post_analysis.failed", error=str(exc))
    rules = getattr(engine, "rules", {})
    return [f for f in findings if passes_savings_gate(f, rules)]


def finding_to_extended_dict(finding: Finding) -> dict[str, Any]:
    """Shape a standard Finding for extended-engine result lists."""
    row = finding.to_dict()
    row.setdefault("annualized_savings_usd", round(float(row.get("estimated_savings_usd") or 0) * 12, 2))
    row.setdefault("confidence_score", 60)
    row.setdefault("action_priority", "P3")
    row.setdefault("impact", row.get("recommendation") or "")
    return row
