"""Network Security Groups optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.nsg_catalog import parse_nsg_arm
from it_services.network_nsg.engine.optimization_rules import (
    NetworkFindingDraft,
    evaluate_nsg_flow_log_cost,
    evaluate_nsg_orphaned,
)


def _append_draft(out, engine, subscription_id, resource, rule, draft: NetworkFindingDraft | None):
    if draft is None or not rule or not rule.enabled:
        return
    out.append(engine._finding(
        rule=rule,
        subscription_id=subscription_id,
        resource=resource,
        detail=draft.detail,
        recommendation=draft.recommendation,
        savings=draft.savings,
        waste_score=draft.waste_score,
        confidence=draft.confidence,
        priority=draft.priority,
        impact=draft.impact,
        evidence=draft.evidence,
    ))


def analyze_nsgs(
    engine,
    subscription_id: str,
    nsgs: list[dict],
    cost_by_resource: dict[str, float] | None = None,
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    orphan_rule = engine.rules.get("NSG_ORPHANED_EXTENDED")
    permissive_rule = engine.rules.get("NSG_PERMISSIVE_EXTENDED")
    flow_log_rule = engine.rules.get("NSG_FLOW_LOG_COST")
    sensitive_ports = {22, 3389, 1433, 5432, 6379, 3306}
    cost_by_resource = cost_by_resource or {}

    for nsg in nsgs:
        props = nsg.get("properties") or {}
        ctx = parse_nsg_arm(nsg)
        monthly = resource_cost(cost_by_resource, nsg.get("id", ""))
        name = nsg.get("name") or ""

        _append_draft(out, engine, subscription_id, nsg, orphan_rule, evaluate_nsg_orphaned(nsg, ctx, monthly, orphan_rule))
        _append_draft(out, engine, subscription_id, nsg, flow_log_rule, evaluate_nsg_flow_log_cost(nsg, ctx, monthly, flow_log_rule))

        if permissive_rule and permissive_rule.enabled:
            risky_rules = []
            for rule_entry in (props.get("securityRules") or []):
                rprops = rule_entry.get("properties") or {}
                if (rprops.get("direction") or "").lower() != "inbound":
                    continue
                if (rprops.get("access") or "").lower() != "allow":
                    continue
                src = rprops.get("sourceAddressPrefix") or ""
                srcs = rprops.get("sourceAddressPrefixes") or []
                is_open = src in ("*", "0.0.0.0/0", "Internet") or any(s in ("*", "0.0.0.0/0", "Internet") for s in srcs)
                if not is_open:
                    continue
                port = rprops.get("destinationPortRange") or ""
                if port == "*" or any(str(p) in {str(x) for x in sensitive_ports} for p in str(port).split(",")):
                    risky_rules.append(rule_entry.get("name") or "unnamed")
            if risky_rules:
                out.append(engine._finding(
                    rule=permissive_rule,
                    subscription_id=subscription_id,
                    resource=nsg,
                    detail=f"NSG '{name}' allows broad inbound access on sensitive ports ({len(risky_rules)} rule(s)).",
                    recommendation="Restrict source IPs, use service tags, or move management access behind a bastion or VPN.",
                    savings=0,
                    waste_score=65,
                    confidence=85,
                    priority="P1",
                    impact="Reduces attack surface and incident-driven cost",
                    evidence={"risky_rules": risky_rules[:5]},
                ))
    return out
