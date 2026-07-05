"""Network Security Groups optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding

def analyze_nsgs(engine, subscription_id: str, nsgs: list[dict]) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    orphan_rule = engine.rules.get("NSG_ORPHANED_EXTENDED")
    permissive_rule = engine.rules.get("NSG_PERMISSIVE_EXTENDED")
    sensitive_ports = {22, 3389, 1433, 5432, 6379, 3306}

    for nsg in nsgs:
        props = nsg.get("properties") or {}
        subnets = props.get("subnets") or []
        nics = props.get("networkInterfaces") or []
        name = nsg.get("name") or ""

        if orphan_rule and orphan_rule.enabled and not subnets and not nics:
            out.append(engine._finding(
                rule=orphan_rule,
                subscription_id=subscription_id,
                resource=nsg,
                detail=f"NSG '{name}' is not associated with any subnet or network interface.",
                recommendation="Delete unused NSGs to reduce governance clutter and misconfiguration risk.",
                savings=0,
                waste_score=28,
                confidence=92,
                priority="P3",
                impact="Inventory hygiene and security posture",
                evidence={"subnet_count": 0, "nic_count": 0},
            ))

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

