"""Load Balancers optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.cost_utils import savings_from_factor
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import is_low_traffic
from app.resource_utilization import monitor_evidence

def analyze_load_balancers(engine, subscription_id: str, load_balancers: list[dict], cost_by_resource: dict[str, float]) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules["LOAD_BALANCER_IDLE_EXTENDED"]
    if not rule.enabled:
        return out
    for lb in load_balancers:
        props = lb.get("properties") or {}
        backends = props.get("backendAddressPools") or []
        if not backends:
            continue
        all_empty = all(
            not (pool.get("properties") or {}).get("backendIPConfigurations")
            and not (pool.get("properties") or {}).get("loadBalancerBackendAddresses")
            for pool in backends
        )
        if all_empty:
            sku_name = ((lb.get("sku") or {}).get("name") or "Basic")
            savings = resource_cost(cost_by_resource, lb.get("id", ""))
            low_traffic = is_low_traffic(lb)
            detail = f"Load balancer '{lb.get('name')}' has backend pools with no active backend addresses."
            if low_traffic is True:
                detail += " Monitor metrics confirm negligible traffic volume."
            out.append(engine._finding(
                rule=rule,
                subscription_id=subscription_id,
                resource=lb,
                detail=detail,
                recommendation="Delete idle load balancers or attach them to active backend resources.",
                savings=savings,
                waste_score=82,
                confidence=confidence_with_monitor(88, lb, boost=8 if low_traffic is True else 0),
                priority="P2",
                impact="Direct network cost reduction and cleaner topology",
                evidence={
                    "determination": "idle_no_backends",
                    "backend_pool_count": len(backends),
                    "all_backends_empty": True,
                    "sku": sku_name,
                    "monthly_cost_usd": savings,
                    "checks": [
                        {
                            "signal": "Backend pools with active targets",
                            "value": len(backends),
                            "threshold": "≥ 1 pool with backends",
                            "passed": False,
                            "status": "fail",
                        },
                    ],
                    "summary": (
                        f"Load balancer has {len(backends)} backend pool(s) but none have "
                        "active backend IP configurations or addresses."
                    ),
                    **monitor_evidence(lb),
                },
            ))
        elif is_low_traffic(lb) is True and not all_empty:
            savings = resource_cost(cost_by_resource, lb.get("id", ""))
            out.append(engine._finding(
                rule=rule,
                subscription_id=subscription_id,
                resource=lb,
                detail=f"Load balancer '{lb.get('name')}' has backends configured but very low traffic in Azure Monitor.",
                recommendation="Consolidate workloads, remove unused backends, or delete the load balancer if no longer required.",
                savings=savings_from_factor(savings, 0.5) if savings > 0 else 0,
                waste_score=68,
                confidence=confidence_with_monitor(80, lb),
                priority="P3",
                impact="Network cost reduction for underutilized load balancer",
                evidence=monitor_evidence(lb, {
                    "determination": "low_traffic",
                    "backend_pool_count": len(backends),
                    "monthly_cost_usd": savings,
                }),
            ))
    return out

