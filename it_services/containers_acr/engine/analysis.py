"""Container Registry optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.acr_utilization import (
    acr_inventory_evidence,
    acr_sku_name,
    acr_threshold_evidence,
    blocks_acr_sku_downgrade,
    is_high_acr_storage,
    is_low_acr_activity,
    is_low_pull_volume,
    is_nonprod_registry,
    meets_acr_savings_gate,
    premium_features_in_use,
    replication_count,
    retention_policy_status,
    storage_used_gb,
)
from app.cost_utils import resource_cost, savings_from_factor
from app.optimizer.core.finding import ExtendedFinding
from it_services.containers_acr.engine.optimization_rules import evaluate_acr_image_retention
from app.resource_utilization import (
    confidence_with_monitor,
    fact_value,
    make_check,
    monitor_facts_status,
    structured_evidence,
    utilization_gate,
)


def _append_metrics_draft(out, engine, subscription_id, resource, rule, draft):
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


def analyze_acr(
    engine,
    subscription_id: str,
    registries: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    premium_rule = engine.rules.get("ACR_PREMIUM_EXTENDED")
    standard_rule = engine.rules.get("ACR_STANDARD_EXTENDED")
    geo_rule = engine.rules.get("ACR_GEO_REPLICATION_EXTENDED")
    storage_rule = engine.rules.get("ACR_STORAGE_HIGH_EXTENDED")
    retention_rule = engine.rules.get("ACR_RETENTION_DISABLED_EXTENDED")

    for reg in registries:
        name = reg.get("name") or ""
        rid = reg.get("id") or ""
        monthly = resource_cost(cost_by_resource, rid)
        sku_name = acr_sku_name(reg)
        lineage = acr_inventory_evidence(reg)

        if premium_rule and premium_rule.enabled and sku_name == "premium":
            if not is_nonprod_registry(reg, nonprod_values=premium_rule.nonprod_tag_values):
                pass
            elif blocks_acr_sku_downgrade(reg):
                pass
            else:
                facts_status = monitor_facts_status(reg, "pull_count")
                if facts_status in {"missing", "partial"}:
                    pass
                elif not utilization_gate(reg, "pull_count", allow_inventory_only=False):
                    pass
                elif is_low_pull_volume(reg, threshold=premium_rule.acr_pull_count_low) is not True:
                    pass
                elif not meets_acr_savings_gate(
                    monthly,
                    min_monthly_savings_usd=premium_rule.min_monthly_savings_usd,
                ):
                    pass
                else:
                    pulls = fact_value(reg, "pull_count")
                    blockers = premium_features_in_use(reg)
                    detail = (
                        f"Container registry '{name}' uses Premium SKU with low pull volume "
                        f"({pulls:,.0f} pulls over 7 days, threshold {premium_rule.acr_pull_count_low:,.0f})."
                    )
                    if blockers:
                        detail += f" Active Premium features: {', '.join(blockers)}."
                    out.append(engine._finding(
                        rule=premium_rule,
                        subscription_id=subscription_id,
                        resource=reg,
                        detail=detail,
                        recommendation=(
                            "Downgrade to Standard or Basic for dev/test registries without private link, "
                            "geo-replication, or network restrictions. Remove Premium-only features before changing SKU."
                        ),
                        savings=savings_from_factor(monthly, 0.5) if monthly > 0 else 25.0,
                        waste_score=58,
                        confidence=confidence_with_monitor(78, reg, boost=12),
                        priority="P2",
                        impact="Registry SKU optimization",
                        evidence=structured_evidence(
                            reg,
                            determination="premium_overkill",
                            summary="Non-production Premium registry shows low pull volume in Azure Monitor.",
                            checks=[
                                make_check(
                                    "Pull count (7d)",
                                    pulls,
                                    f"< {premium_rule.acr_pull_count_low:,.0f}",
                                    passed=True,
                                ),
                            ],
                            extra={
                                **lineage,
                                **acr_threshold_evidence(premium_rule),
                            },
                        ),
                    ))

        if standard_rule and standard_rule.enabled and sku_name == "standard":
            if blocks_acr_sku_downgrade(reg):
                pass
            elif monitor_facts_status(reg, "pull_count") in {"missing", "partial"}:
                pass
            elif not utilization_gate(reg, "pull_count", allow_inventory_only=False):
                pass
            elif is_low_pull_volume(reg, threshold=standard_rule.acr_pull_count_low) is not True:
                pass
            elif is_high_acr_storage(reg, min_gb=standard_rule.acr_storage_high_gb) is True:
                pass
            elif not meets_acr_savings_gate(
                monthly,
                min_monthly_savings_usd=standard_rule.min_monthly_savings_usd,
            ):
                pass
            else:
                pulls = fact_value(reg, "pull_count")
                storage_gb = storage_used_gb(reg)
                out.append(engine._finding(
                    rule=standard_rule,
                    subscription_id=subscription_id,
                    resource=reg,
                    detail=(
                        f"Container registry '{name}' uses Standard SKU with low activity "
                        f"({pulls:,.0f} pulls, {storage_gb:g} GB storage used)."
                    ),
                    recommendation="Downgrade to Basic when private link and geo-replication are not required.",
                    savings=savings_from_factor(monthly, 0.35) if monthly > 0 else 12.0,
                    waste_score=50,
                    confidence=confidence_with_monitor(74, reg, boost=10),
                    priority="P3",
                    impact="Registry SKU optimization",
                    evidence={
                        **lineage,
                        **acr_threshold_evidence(standard_rule),
                    },
                ))

        if geo_rule and geo_rule.enabled:
            rep_count = replication_count(reg)
            if rep_count > 0 and meets_acr_savings_gate(
                monthly,
                min_monthly_savings_usd=geo_rule.min_monthly_savings_usd,
            ):
                regions = lineage.get("replication_regions") or []
                region_text = f" across {', '.join(regions)}" if regions else ""
                out.append(engine._finding(
                    rule=geo_rule,
                    subscription_id=subscription_id,
                    resource=reg,
                    detail=(
                        f"Container registry '{name}' has {rep_count} geo-replication region(s){region_text}."
                    ),
                    recommendation="Disable geo-replication unless multi-region pull performance is required.",
                    savings=savings_from_factor(monthly, 0.35) if monthly > 0 else 15.0,
                    waste_score=48,
                    confidence=82,
                    priority="P3",
                    impact="Reduces replicated storage and transfer charges",
                    evidence={
                        **lineage,
                        "replication_count": rep_count,
                        **acr_threshold_evidence(geo_rule),
                    },
                ))

        if storage_rule and storage_rule.enabled:
            if monitor_facts_status(reg, "storage_used_bytes") in {"missing", "partial"}:
                pass
            elif is_high_acr_storage(reg, min_gb=storage_rule.acr_storage_high_gb) is not True:
                pass
            elif is_low_acr_activity(
                reg,
                pull_threshold=storage_rule.acr_pull_count_low,
                push_threshold=storage_rule.acr_push_count_low,
            ) is not True:
                pass
            elif not meets_acr_savings_gate(
                monthly,
                min_monthly_savings_usd=storage_rule.min_monthly_savings_usd,
            ):
                pass
            else:
                storage_gb = storage_used_gb(reg) or 0
                out.append(engine._finding(
                    rule=storage_rule,
                    subscription_id=subscription_id,
                    resource=reg,
                    detail=(
                        f"Container registry '{name}' uses {storage_gb:g} GB storage "
                        f"(threshold {storage_rule.acr_storage_high_gb:g} GB) with low pull/push activity."
                    ),
                    recommendation=(
                        "Review image cleanup: enable untagged manifest retention (Premium), schedule "
                        "acr purge for stale tagged images, and delete unused repositories."
                    ),
                    savings=savings_from_factor(monthly, 0.25) if monthly > 0 else 8.0,
                    waste_score=44,
                    confidence=confidence_with_monitor(70, reg, boost=8),
                    priority="P3",
                    impact="Reduces registry storage spend",
                    evidence={
                        **lineage,
                        **acr_threshold_evidence(storage_rule),
                    },
                ))

        if retention_rule and retention_rule.enabled and sku_name == "premium":
            enabled, days = retention_policy_status(reg)
            if enabled:
                pass
            elif is_high_acr_storage(reg, min_gb=retention_rule.acr_storage_high_gb) is not True:
                pass
            elif not meets_acr_savings_gate(
                monthly,
                min_monthly_savings_usd=retention_rule.min_monthly_savings_usd,
            ):
                pass
            else:
                storage_gb = storage_used_gb(reg)
                out.append(engine._finding(
                    rule=retention_rule,
                    subscription_id=subscription_id,
                    resource=reg,
                    detail=(
                        f"Container registry '{name}' has high storage"
                        f"{f' ({storage_gb:g} GB)' if storage_gb is not None else ''} "
                        "and untagged manifest retention is disabled."
                    ),
                    recommendation=(
                        "Enable the untagged manifest retention policy (Premium) or schedule acr purge "
                        "tasks to control storage growth."
                    ),
                    savings=0.0,
                    waste_score=36,
                    confidence=76,
                    priority="P3",
                    impact="Storage governance — prevents unbounded growth",
                    evidence={
                        **lineage,
                        "retention_policy_enabled": False,
                        **acr_threshold_evidence(retention_rule),
                    },
                ))

        retention_ext_rule = engine.rules.get("ACR_IMAGE_RETENTION_EXTENDED")
        _append_metrics_draft(
            out, engine, subscription_id, reg, retention_ext_rule,
            evaluate_acr_image_retention(reg, monthly, retention_ext_rule),
        )

    return out
