"""Advanced network optimization rules (ExpressRoute, DDoS, Traffic Manager, Front Door)."""

from __future__ import annotations

from app.cost_utils import resource_cost
from app.optimizer.standard_finding import Finding


def _gc(engine):
    return getattr(engine, "global_config", None)


def analyze_network_advanced(
    engine,
    subscription_id: str,
    resources_by_type: dict[str, list[dict]],
    cost_by_resource: dict[str, float] | None = None,
) -> list[Finding]:
    out: list[Finding] = []
    gc = _gc(engine)
    ddos_rule = engine.rules.get("NETWORK_DDOS_PLAN_REVIEW")
    tm_rule = engine.rules.get("NETWORK_TRAFFIC_MANAGER_IDLE")
    er_rule = engine.rules.get("NETWORK_EXPRESSROUTE_REVIEW")

    for resource in resources_by_type.get("network/publicip", []):
        props = resource.get("properties") or {}
        if not ddos_rule or not ddos_rule.enabled:
            break
        if props.get("ddosSettings", {}).get("protectionMode") == "Enabled":
            monthly = resource_cost(cost_by_resource or {}, resource.get("id", ""))
            if monthly >= getattr(ddos_rule, "min_monthly_savings_usd", 5.0):
                out.append(Finding(
                    ddos_rule, resource,
                    detail=f"Public IP '{resource.get('name')}' has DDoS Network Protection enabled.",
                    recommendation="Confirm DDoS Standard is required; disable on non-critical endpoints.",
                    savings=round(monthly * 0.5, 2),
                    score=45,
                    evidence={"protection_mode": "Enabled"},
                    global_config=gc,
                ))

    for resource in resources_by_type.get("network/trafficmanager", []):
        if not tm_rule or not tm_rule.enabled:
            break
        profiles = (resource.get("properties") or {}).get("profileStatus") or "Enabled"
        monthly = resource_cost(cost_by_resource or {}, resource.get("id", ""))
        if profiles and monthly >= getattr(tm_rule, "min_monthly_savings_usd", 1.0):
            out.append(Finding(
                tm_rule, resource,
                detail=f"Traffic Manager profile '{resource.get('name')}' is active — validate endpoint health and usage.",
                recommendation="Remove unused profiles or consolidate DNS routing.",
                savings=round(monthly * 0.25, 2),
                score=40,
                evidence={"status": profiles},
                global_config=gc,
            ))

    for resource in resources_by_type.get("network/expressroute", []):
        if not er_rule or not er_rule.enabled:
            break
        props = resource.get("properties") or {}
        state = str(props.get("provisioningState") or props.get("serviceProviderProvisioningState") or "")
        monthly = resource_cost(cost_by_resource or {}, resource.get("id", ""))
        if state.lower() in {"succeeded", "enabled", "provisioned"} and monthly >= getattr(er_rule, "min_monthly_savings_usd", 50.0):
            peerings = props.get("peerings") or []
            out.append(Finding(
                er_rule, resource,
                detail=f"ExpressRoute circuit '{resource.get('name')}' costs ${monthly:,.2f}/mo — review bandwidth tier and peering usage.",
                recommendation="Right-size circuit bandwidth or consolidate peerings if utilization is low.",
                savings=round(monthly * 0.15, 2),
                score=48,
                evidence={"monthly_cost_usd": monthly, "peering_count": len(peerings), "state": state},
                global_config=gc,
            ))

    return out
