"""NAT Gateways optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import fact_value
from app.resource_utilization import is_low_traffic
from app.resource_utilization import make_check
from app.resource_utilization import structured_evidence


def analyze_nat_gateways(engine, subscription_id: str, nat_gateways: list[dict], cost_by_resource: dict[str, float]) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("NAT_GATEWAY_IDLE_EXTENDED")
    if not rule or not rule.enabled:
        return out
    for nat in nat_gateways:
        props = nat.get("properties") or {}
        subnets = props.get("subnets") or []
        subnet_count = len(subnets)
        name = nat.get("name") or ""
        nat_cost = resource_cost(cost_by_resource, nat.get("id", ""))
        low_traffic = is_low_traffic(nat)
        snat = fact_value(nat, "snat_connection_count")
        low_snat = snat is not None and snat < 10.0

        if subnet_count == 0:
            detail = f"NAT Gateway '{name}' has no subnet associations."
            if low_traffic is True:
                detail = f"NAT Gateway '{name}' shows no meaningful traffic in Azure Monitor."
            out.append(engine._finding(
                rule=rule,
                subscription_id=subscription_id,
                resource=nat,
                detail=detail,
                recommendation="Delete idle NAT Gateway or attach subnets that require outbound SNAT.",
                savings=nat_cost,
                waste_score=80,
                confidence=confidence_with_monitor(93, nat, boost=6 if low_traffic is True else 0),
                priority="P2",
                impact="Direct idle network appliance cost",
                evidence=structured_evidence(
                    nat,
                    determination="unassociated_nat",
                    summary="NAT Gateway has no subnet associations and is pure idle spend.",
                    checks=[
                        make_check("Subnet associations", subnet_count, "≥ 1", passed=False),
                    ],
                    extra={"subnet_count": subnet_count, "monthly_cost_usd": nat_cost},
                ),
            ))
            continue

        if low_traffic is True and low_snat:
            out.append(engine._finding(
                rule=rule,
                subscription_id=subscription_id,
                resource=nat,
                detail=f"NAT Gateway '{name}' is associated but shows negligible traffic in Azure Monitor.",
                recommendation="Remove unused subnet associations or delete the NAT Gateway if outbound SNAT is no longer required.",
                savings=nat_cost,
                waste_score=74,
                confidence=confidence_with_monitor(86, nat),
                priority="P2",
                impact="Reclaim idle NAT Gateway capacity",
                evidence=structured_evidence(
                    nat,
                    determination="associated_low_traffic",
                    summary="NAT Gateway has subnet associations but negligible byte volume and SNAT connections.",
                    checks=[
                        make_check("Byte count", fact_value(nat, "byte_count"), "Low", passed=True),
                        make_check("SNAT connections", snat, "< 10", passed=low_snat or snat is None),
                        make_check("Subnet associations", subnet_count, "≥ 1", passed=True),
                    ],
                    extra={"subnet_count": subnet_count, "monthly_cost_usd": nat_cost},
                ),
            ))
    return out
