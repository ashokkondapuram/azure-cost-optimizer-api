"""Networking (Firewall, CDN, Private Link) optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.cost_utils import savings_from_factor
from app.resource_utilization import make_check
from app.resource_utilization import structured_evidence


def analyze_firewalls(
    engine,
    subscription_id: str,
    firewalls: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("FIREWALL_FIXED_COST_EXTENDED")
    if not rule or not rule.enabled:
        return out
    for fw in firewalls:
        name = fw.get("name") or ""
        monthly = resource_cost(cost_by_resource, fw.get("id", ""))
        min_spend = float(getattr(rule, "min_monthly_savings_usd", 200.0) or 200.0)
        if monthly < min_spend:
            continue
        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource=fw,
            detail=f"Firewall resource '{name}' has MTD spend of ${monthly:,.2f}.",
            recommendation="Confirm hub topology requirements; use NVAs or secured virtual hubs only where policy mandates a dedicated firewall SKU.",
            savings=savings_from_factor(monthly, 0.10),
            waste_score=52,
            confidence=58,
            priority="P2",
            impact="Validate dedicated firewall necessity",
            evidence={"monthly_cost_usd": monthly},
        ))
    return out


def analyze_cdn_profiles(
    engine,
    subscription_id: str,
    profiles: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("CDN_EGRESS_EXTENDED")
    if not rule or not rule.enabled:
        return out
    for profile in profiles:
        name = profile.get("name") or ""
        monthly = resource_cost(cost_by_resource, profile.get("id", ""))
        min_spend = float(getattr(rule, "min_monthly_savings_usd", 80.0) or 80.0)
        if monthly < min_spend:
            continue
        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource=profile,
            detail=f"CDN or Front Door profile '{name}' has MTD spend of ${monthly:,.2f}.",
            recommendation="Review origin egress, caching rules, rule sets, and consolidate profiles across environments where possible.",
            savings=savings_from_factor(monthly, 0.15),
            waste_score=48,
            confidence=60,
            priority="P2",
            evidence={"monthly_cost_usd": monthly},
        ))
    return out


def _facts(resource: dict) -> dict[str, Any]:
    return resource.get("_technical_facts") or {}


def analyze_vnets(
    engine,
    subscription_id: str,
    vnets: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("VNET_PEERING_REVIEW_EXTENDED")
    if not rule or not rule.enabled:
        return out
    min_savings = float(getattr(rule, "min_monthly_savings_usd", 10.0) or 10.0)
    for vnet in vnets:
        props = vnet.get("properties") or {}
        facts = _facts(vnet)
        peering_count = int(
            facts.get("peering_count")
            if facts.get("peering_count") is not None
            else len(props.get("virtualNetworkPeerings") or [])
        )
        if peering_count <= 0:
            continue
        name = vnet.get("name") or ""
        monthly = resource_cost(cost_by_resource, vnet.get("id", ""))
        if monthly > 0 and monthly < min_savings:
            continue
        savings = savings_from_factor(monthly, 0.10) if monthly > 0 else 0
        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource=vnet,
            detail=(
                f"Virtual network '{name}' has {peering_count} peering(s)"
                + (f" and MTD network spend of ${monthly:,.2f}." if monthly > 0 else ".")
            ),
            recommendation="Review cross-region peering and data transfer paths; consolidate VNets or use hub-spoke designs to reduce recurring egress.",
            savings=savings,
            waste_score=42,
            confidence=55,
            priority="P3",
            impact="Reduce peering and cross-region transfer cost",
            evidence=structured_evidence(
                vnet,
                determination="peering_review",
                summary="Virtual network has active peerings that may drive recurring transfer spend.",
                checks=[make_check("Peering count", peering_count, "≥ 1", passed=True)],
                extra={"peering_count": peering_count, "monthly_cost_usd": monthly},
            ),
        ))
    return out


def analyze_private_endpoints(
    engine,
    subscription_id: str,
    endpoints: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    failed_rule = engine.rules.get("PRIVATE_ENDPOINT_FAILED_EXTENDED")
    orphan_rule = engine.rules.get("PRIVATE_ENDPOINT_ORPHAN_EXTENDED")
    if not failed_rule and not orphan_rule:
        return out

    for endpoint in endpoints:
        props = endpoint.get("properties") or {}
        facts = _facts(endpoint)
        name = endpoint.get("name") or ""
        monthly = resource_cost(cost_by_resource, endpoint.get("id", ""))
        connection_state = str(
            facts.get("connection_state")
            or props.get("provisioningState")
            or ""
        ).lower()
        target_id = facts.get("target_resource_id")

        if failed_rule and failed_rule.enabled and connection_state in {
            "rejected", "failed", "disconnected",
        }:
            out.append(engine._finding(
                rule=failed_rule,
                subscription_id=subscription_id,
                resource=endpoint,
                detail=f"Private endpoint '{name}' connection state is {connection_state}.",
                recommendation="Fix the private link connection or delete the endpoint to stop hourly charges.",
                savings=monthly if monthly > 0 else savings_from_factor(25.0, 0.95),
                waste_score=72,
                confidence=88,
                priority="P1",
                impact="Stop billing on failed private endpoint connections",
                evidence=structured_evidence(
                    endpoint,
                    determination="connection_failed",
                    summary="Private endpoint connection is not approved.",
                    checks=[make_check("Connection state", connection_state, "Approved", passed=False)],
                    extra={"connection_state": connection_state, "monthly_cost_usd": monthly},
                ),
            ))
            continue

        min_orphan = float(getattr(orphan_rule, "min_monthly_savings_usd", 5.0) or 5.0) if orphan_rule else 5.0
        if orphan_rule and orphan_rule.enabled and not target_id:
            if monthly >= min_orphan or monthly == 0:
                out.append(engine._finding(
                    rule=orphan_rule,
                    subscription_id=subscription_id,
                    resource=endpoint,
                    detail=f"Private endpoint '{name}' has no approved target connection.",
                    recommendation="Delete orphaned private endpoints after validating DNS zone group dependencies.",
                    savings=monthly if monthly > 0 else savings_from_factor(25.0, 0.90),
                    waste_score=58,
                    confidence=80,
                    priority="P2",
                    impact="Remove unused private endpoint hourly charges",
                    evidence=structured_evidence(
                        endpoint,
                        determination="orphaned_endpoint",
                        summary="Private endpoint lacks an approved private link target.",
                        checks=[
                            make_check("Target resource", target_id, "Present", passed=bool(target_id)),
                            make_check("Connection state", connection_state or "unknown", "Approved", passed=False),
                        ],
                        extra={"monthly_cost_usd": monthly},
                    ),
                ))
    return out


def analyze_private_link_services(
    engine,
    subscription_id: str,
    services: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("PRIVATE_LINK_UNUSED_EXTENDED")
    if not rule or not rule.enabled:
        return out
    min_savings = float(getattr(rule, "min_monthly_savings_usd", 5.0) or 5.0)
    for service in services:
        props = service.get("properties") or {}
        facts = _facts(service)
        connection_count = int(
            facts.get("connection_count")
            if facts.get("connection_count") is not None
            else len(props.get("privateEndpointConnections") or [])
        )
        if connection_count > 0:
            continue
        name = service.get("name") or ""
        monthly = resource_cost(cost_by_resource, service.get("id", ""))
        if monthly > 0 and monthly < min_savings:
            continue
        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource=service,
            detail=f"Private link service '{name}' has no private endpoint connections.",
            recommendation="Delete unused private link services or onboard consumers via approved private endpoints.",
            savings=monthly if monthly > 0 else 0,
            waste_score=54,
            confidence=78,
            priority="P2",
            impact="Remove idle private link service resources",
            evidence=structured_evidence(
                service,
                determination="unused_private_link",
                summary="Private link service has zero endpoint connections.",
                checks=[make_check("Endpoint connections", connection_count, "≥ 1", passed=False)],
                extra={"connection_count": connection_count, "monthly_cost_usd": monthly},
            ),
        ))
    return out


def analyze_private_dns_zones(
    engine,
    subscription_id: str,
    zones: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules.get("PRIVATE_DNS_EMPTY_EXTENDED")
    if not rule or not rule.enabled:
        return out
    max_default_records = int(getattr(rule, "private_dns_max_default_record_sets", 2) or 2)
    for zone in zones:
        props = zone.get("properties") or {}
        facts = _facts(zone)
        record_count = facts.get("record_set_count")
        if record_count is None:
            record_count = props.get("numberOfRecordSets")
        is_empty = None
        if record_count is not None:
            try:
                is_empty = int(record_count) <= max_default_records
            except (TypeError, ValueError):
                is_empty = False
        if not is_empty:
            continue
        name = zone.get("name") or ""
        monthly = resource_cost(cost_by_resource, zone.get("id", ""))
        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource=zone,
            detail=f"Private DNS zone '{name}' has no custom record sets.",
            recommendation="Delete empty private DNS zones or attach them to active private endpoints.",
            savings=monthly if monthly > 0 else 0,
            waste_score=40,
            confidence=75,
            priority="P3",
            impact="Clean up unused private DNS zones",
            evidence=structured_evidence(
                zone,
                determination="empty_dns_zone",
                summary="Private DNS zone only contains default SOA/NS records.",
                extra={
                    "record_set_count": record_count,
                    "private_dns_max_default_record_sets": max_default_records,
                    "monthly_cost_usd": monthly,
                },
            ),
        ))
    return out
