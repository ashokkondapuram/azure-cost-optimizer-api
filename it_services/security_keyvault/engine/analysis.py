"""Key Vault optimization analysis rules."""
from __future__ import annotations

from app.cost_utils import resource_cost, savings_from_factor
from app.keyvault_utilization import (
    blocks_premium_downgrade,
    is_high_keyvault_ops,
    is_idle_keyvault,
    is_nonprod_vault,
    kv_inventory_evidence,
    kv_sku_name,
    kv_threshold_evidence,
    meets_kv_savings_gate,
    protection_baseline_gap,
    purge_protection_enabled,
    soft_delete_enabled,
)
from app.optimizer.core.finding import ExtendedFinding
from app.resource_utilization import (
    confidence_with_monitor,
    fact_value,
    make_check,
    monitor_facts_status,
    structured_evidence,
    utilization_gate,
)


def analyze_keyvaults(
    engine,
    subscription_id: str,
    keyvaults: list[dict],
    cost_by_resource: dict[str, float],
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    protection_rule = engine.rules.get("KEYVAULT_PROTECTION_EXTENDED")
    idle_rule = engine.rules.get("KEYVAULT_IDLE_EXTENDED")
    premium_rule = engine.rules.get("KEYVAULT_PREMIUM_EXTENDED")
    high_ops_rule = engine.rules.get("KEYVAULT_HIGH_OPS_EXTENDED")

    for vault in keyvaults:
        name = vault.get("name") or ""
        rid = vault.get("id") or ""
        monthly = resource_cost(cost_by_resource, rid)
        lineage = kv_inventory_evidence(vault)
        soft_delete = soft_delete_enabled(vault)
        purge_protection = purge_protection_enabled(vault)

        if protection_rule and protection_rule.enabled and protection_baseline_gap(vault):
            out.append(engine._finding(
                rule=protection_rule,
                subscription_id=subscription_id,
                resource=vault,
                detail=f"Key Vault '{name}' does not meet the recommended deletion protection baseline.",
                recommendation=(
                    "Enable soft delete and purge protection for production vaults "
                    "after validating operational recovery procedures."
                ),
                savings=0,
                waste_score=18,
                confidence=92,
                priority="P1",
                impact="Prevents accidental secret loss and costly recovery incidents",
                evidence=structured_evidence(
                    vault,
                    determination="protection_baseline_gap",
                    summary="Key Vault is missing soft delete or purge protection.",
                    checks=[
                        make_check("Soft delete enabled", soft_delete, "true", passed=soft_delete is not False),
                        make_check("Purge protection enabled", purge_protection, "true", passed=purge_protection is True),
                    ],
                    extra={
                        **lineage,
                        **kv_threshold_evidence(protection_rule),
                    },
                ),
            ))

        if idle_rule and idle_rule.enabled:
            facts_status = monitor_facts_status(vault, "api_hits")
            if facts_status == "available" and utilization_gate(vault, "api_hits", allow_inventory_only=False):
                if is_idle_keyvault(vault, threshold=idle_rule.kv_api_hits_idle) is True:
                    if meets_kv_savings_gate(monthly, min_monthly_savings_usd=idle_rule.min_monthly_savings_usd):
                        hits = fact_value(vault, "api_hits")
                        out.append(engine._finding(
                            rule=idle_rule,
                            subscription_id=subscription_id,
                            resource=vault,
                            detail=(
                                f"Key Vault '{name}' shows very low API activity "
                                f"({hits:,.0f} hits over 7 days, threshold {idle_rule.kv_api_hits_idle:,.0f})."
                            ),
                            recommendation=(
                                "Consolidate secrets into an active vault or delete unused vaults "
                                "after validating dependencies."
                            ),
                            savings=monthly if monthly > 0 else 0,
                            waste_score=28,
                            confidence=confidence_with_monitor(70, vault),
                            priority="P3",
                            impact="Reduces unused vault operations and management overhead",
                            evidence=structured_evidence(
                                vault,
                                determination="idle_vault",
                                summary="Key Vault has negligible API hits over the monitor window.",
                                checks=[
                                    make_check(
                                        "API hits (7d)",
                                        hits,
                                        f"< {idle_rule.kv_api_hits_idle:,.0f}",
                                        passed=True,
                                    ),
                                ],
                                extra={
                                    **lineage,
                                    "monthly_cost_usd": monthly,
                                    **kv_threshold_evidence(idle_rule),
                                },
                            ),
                        ))

        if premium_rule and premium_rule.enabled and kv_sku_name(vault) == "premium":
            if not blocks_premium_downgrade(
                vault,
                nonprod_values=premium_rule.nonprod_tag_values,
                idle_threshold=premium_rule.kv_api_hits_idle,
            ):
                facts_status = monitor_facts_status(vault, "api_hits")
                if facts_status == "available" and utilization_gate(vault, "api_hits", allow_inventory_only=False):
                    if is_idle_keyvault(vault, threshold=premium_rule.kv_api_hits_idle) is True:
                        if meets_kv_savings_gate(
                            monthly,
                            min_monthly_savings_usd=premium_rule.min_monthly_savings_usd,
                        ):
                            hits = fact_value(vault, "api_hits")
                            out.append(engine._finding(
                                rule=premium_rule,
                                subscription_id=subscription_id,
                                resource=vault,
                                detail=(
                                    f"Key Vault '{name}' uses Premium SKU with low API activity "
                                    f"({hits:,.0f} hits over 7 days)."
                                ),
                                recommendation=(
                                    "Downgrade to Standard if the vault stores secrets or certificates only "
                                    "and has no HSM-backed keys. Validate key inventory before changing SKU."
                                ),
                                savings=savings_from_factor(monthly, 0.3) if monthly > 0 else 5.0,
                                waste_score=42,
                                confidence=confidence_with_monitor(72, vault, boost=8),
                                priority="P3",
                                impact="Avoids HSM key monthly charges when Premium is not required",
                                evidence={
                                    **lineage,
                                    **kv_threshold_evidence(premium_rule),
                                },
                            ))

        if high_ops_rule and high_ops_rule.enabled:
            facts_status = monitor_facts_status(vault, "api_hits")
            if facts_status == "available" and utilization_gate(vault, "api_hits", allow_inventory_only=False):
                if is_high_keyvault_ops(vault, threshold=high_ops_rule.kv_api_hits_high) is True:
                    if meets_kv_savings_gate(
                        monthly,
                        min_monthly_savings_usd=high_ops_rule.min_monthly_savings_usd,
                    ):
                        hits = fact_value(vault, "api_hits")
                        out.append(engine._finding(
                            rule=high_ops_rule,
                            subscription_id=subscription_id,
                            resource=vault,
                            detail=(
                                f"Key Vault '{name}' has high API volume "
                                f"({hits:,.0f} hits over 7 days, threshold {high_ops_rule.kv_api_hits_high:,.0f})."
                            ),
                            recommendation=(
                                "Cache secrets in application memory (30–60 minutes), use Key Vault references "
                                "in App Service, and reduce polling frequency to lower operation charges."
                            ),
                            savings=savings_from_factor(monthly, 0.25) if monthly > 0 else 8.0,
                            waste_score=38,
                            confidence=confidence_with_monitor(76, vault),
                            priority="P3",
                            impact="Reduces per-operation Key Vault charges",
                            evidence=structured_evidence(
                                vault,
                                determination="high_api_volume",
                                summary="Key Vault API hits exceed the high-ops threshold.",
                                checks=[
                                    make_check(
                                        "API hits (7d)",
                                        hits,
                                        f"≥ {high_ops_rule.kv_api_hits_high:,.0f}",
                                        passed=True,
                                    ),
                                ],
                                extra={
                                    **lineage,
                                    "monthly_cost_usd": monthly,
                                    **kv_threshold_evidence(high_ops_rule),
                                },
                            ),
                        ))

    return out
