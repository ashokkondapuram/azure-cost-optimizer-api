"""Public IPs optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import fact_value
from app.resource_utilization import is_idle_public_ip_traffic
from app.resource_utilization import make_check
from app.resource_utilization import monitor_facts_status
from app.resource_utilization import structured_evidence


def analyze_public_ips(engine, subscription_id: str, public_ips: list[dict], cost_by_resource: dict[str, float]) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules["PUBLIC_IP_IDLE_EXTENDED"]
    if not rule.enabled:
        return out
    for ip in public_ips:
        props = ip.get("properties") or {}
        assoc = props.get("ipConfiguration") or props.get("natGateway")
        alloc = props.get("publicIPAllocationMethod") or ""
        ip_cost = resource_cost(cost_by_resource, ip.get("id", ""))
        name = ip.get("name") or ""

        if alloc == "Static" and not assoc:
            out.append(engine._finding(
                rule=rule,
                subscription_id=subscription_id,
                resource=ip,
                detail=f"Public IP '{name}' is static and not associated to any live resource.",
                recommendation="Delete idle static public IPs after confirming no DNS or failover dependency exists.",
                savings=ip_cost,
                waste_score=80,
                confidence=95,
                priority="P2",
                impact="Low-risk direct network savings",
                evidence=structured_evidence(
                    ip,
                    determination="ip_unassociated",
                    summary="Static public IP has no association to a NIC, load balancer, or NAT gateway.",
                    checks=[
                        make_check("Allocation method", alloc, "Static", passed=alloc == "Static"),
                        make_check("Resource association", bool(assoc), "Associated", passed=bool(assoc)),
                    ],
                    extra={"allocation": alloc, "monthly_cost_usd": ip_cost},
                ),
            ))
            continue

        traffic_idle = is_idle_public_ip_traffic(ip)
        facts_status = monitor_facts_status(ip, "byte_count", "packet_count")
        if alloc == "Static" and assoc and facts_status == "available" and traffic_idle is True:
            out.append(engine._finding(
                rule=rule,
                subscription_id=subscription_id,
                resource=ip,
                detail=f"Public IP '{name}' is associated but shows negligible traffic in Azure Monitor.",
                recommendation="Review whether the IP is still required; detach and delete if the workload no longer needs a public endpoint.",
                savings=ip_cost,
                waste_score=72,
                confidence=confidence_with_monitor(88, ip),
                priority="P2",
                impact="Reclaim unused public IP capacity",
                evidence=structured_evidence(
                    ip,
                    determination="associated_low_traffic",
                    summary="Associated static public IP shows negligible byte and packet volume over the monitor window.",
                    checks=[
                        make_check("Byte count", fact_value(ip, "byte_count"), "< 1,000", passed=True),
                        make_check("Packet count", fact_value(ip, "packet_count"), "< 100", passed=True),
                    ],
                    extra={"allocation": alloc, "monthly_cost_usd": ip_cost},
                ),
            ))
    return out
