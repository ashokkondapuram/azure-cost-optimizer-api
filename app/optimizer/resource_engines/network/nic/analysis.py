"""Network Interfaces optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import fact_value
from app.resource_utilization import make_check
from app.resource_utilization import structured_evidence


def analyze_network_interfaces(engine, subscription_id: str, nics: list[dict]) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("NIC_ORPHANED_EXTENDED")
    if not rule or not rule.enabled:
        return out
    for nic in nics:
        props = nic.get("properties") or {}
        facts = nic.get("_technical_facts") or {}
        has_vm = bool(props.get("virtualMachine") or facts.get("has_vm"))
        has_pe = bool(props.get("privateEndpoint") or facts.get("has_private_endpoint"))
        if has_vm or has_pe:
            continue
        rx = fact_value(nic, "bytes_received_rate")
        tx = fact_value(nic, "bytes_sent_rate")
        traffic_idle = (
            (rx is None or rx < 100.0) and (tx is None or tx < 100.0)
            if rx is not None or tx is not None
            else None
        )
        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource=nic,
            detail=f"NIC '{nic.get('name')}' is orphaned and not attached to a compute resource.",
            recommendation="Delete orphaned NICs after validating no private-link or firewall dependency remains.",
            savings=0,
            waste_score=52,
            confidence=confidence_with_monitor(91, nic, boost=6 if traffic_idle is True else 0),
            priority="P3",
            impact="Inventory hygiene and minor operational savings",
            evidence=structured_evidence(
                nic,
                determination="orphaned_nic",
                summary="Network interface is not attached to a VM or private endpoint.",
                checks=[
                    make_check("VM attachment", has_vm, "Attached", passed=False),
                    make_check("Private endpoint", has_pe, "Attached", passed=False),
                    make_check(
                        "Ingress traffic (bytes/s)",
                        rx,
                        "< 100 when monitored",
                        passed=traffic_idle is not False,
                    ),
                ],
                extra={"has_vm": has_vm, "has_private_endpoint": has_pe},
            ),
        ))
    return out
