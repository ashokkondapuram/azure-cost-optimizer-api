"""Governance and compliance oriented optimization rules."""

from __future__ import annotations

from app.optimizer.standard_finding import Finding


def analyze_governance(
    engine,
    subscription_id: str,
    resources: list[dict],
) -> list[Finding]:
    out: list[Finding] = []
    tag_rule = engine.rules.get("GOVERNANCE_TAG_ENFORCEMENT")
    if not tag_rule or not tag_rule.enabled:
        return out

    gc = getattr(engine, "global_config", None)
    required = {"environment", "owner", "costcenter", "cost-center"}
    for resource in resources:
        tags = {k.lower(): v for k, v in (resource.get("tags") or {}).items()}
        missing = sorted(required - set(tags))
        if not missing:
            continue
        out.append(Finding(
            tag_rule,
            resource,
            detail=f"Resource '{resource.get('name')}' is missing required tags: {', '.join(missing)}.",
            recommendation="Apply mandatory tags to improve chargeback and policy compliance.",
            savings=0,
            score=35,
            evidence={"missing_tags": missing},
            global_config=gc,
        ))
    return out
