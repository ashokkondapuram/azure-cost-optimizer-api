"""Unified VM cost recommendation — Advisor SKU alignment + engine savings math.

Advisor provides target SKU and optional reference savings. The engine always
computes savings from retail/run-rate pricing. A zero or missing Advisor
savingsAmount must never zero out engine-computed savings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.advisor_vm_targets import AdvisorVmTarget
from app.azure_retail_pricing import estimate_vm_sku_savings, vm_os_type
from app.cost_utils import project_mtd_to_monthly_run_rate
from app.pricing.savings_calculator import enrich_pricing_payload, savings_from_retail_or_none
from app.vm_sizing import VmSizingRecommendation, parse_vm_sku

SkuAgreement = Literal["agree", "advisor_only", "engine_only", "disagree", "none"]
SkuSource = Literal["azure_advisor", "engine", "none"]
VmAction = Literal["rightsize", "decommission", "none"]


@dataclass
class VmCostDecision:
    action: VmAction
    current_sku: str
    target_sku: str | None
    sku_source: SkuSource
    engine_target_sku: str | None
    advisor_target_sku: str | None
    sku_agreement: SkuAgreement
    monthly_savings: float
    pricing: dict[str, Any] = field(default_factory=dict)
    advisor_savings_reference: float | None = None
    sizing: VmSizingRecommendation | None = None
    reasons: list[str] = field(default_factory=list)

    def evidence(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "sku_agreement": self.sku_agreement,
            "engine_target_sku": self.engine_target_sku,
            "advisor_target_sku": self.advisor_target_sku,
            "sku_source": self.sku_source if self.sku_source != "none" else None,
            "advisor_savings_monthly": self.advisor_savings_reference,
            "savings_source": "engine_pricing",
            **self.pricing,
        }
        if self.sku_agreement == "agree":
            out["sku_alignment_note"] = "Engine agrees with Azure Advisor target SKU."
        elif self.sku_agreement == "disagree":
            out["sku_alignment_note"] = (
                "Engine suggests a different SKU than Azure Advisor — review before resizing."
            )
        elif self.sku_agreement == "advisor_only":
            out["sku_alignment_note"] = "Target SKU from Azure Advisor cost recommendation."
        return {k: v for k, v in out.items() if v is not None}


def _sku_agreement(engine_sku: str | None, advisor_sku: str | None) -> SkuAgreement:
    if advisor_sku and engine_sku:
        return "agree" if advisor_sku.lower() == engine_sku.lower() else "disagree"
    if advisor_sku:
        return "advisor_only"
    if engine_sku:
        return "engine_only"
    return "none"


def _sizing_from_target(
    current_sku: str,
    target_sku: str,
    *,
    reasons: list[str],
    confidence: int = 70,
) -> VmSizingRecommendation:
    parsed_cur = parse_vm_sku(current_sku)
    parsed_tgt = parse_vm_sku(target_sku)
    action = "downgrade"
    direction: Literal["down", "up", "lateral", "none"] = "down"
    if parsed_cur and parsed_tgt:
        if parsed_tgt.family != parsed_cur.family:
            action = "cross_family"
            direction = "lateral"
        elif parsed_tgt.vcpus > parsed_cur.vcpus:
            action = "upgrade"
            direction = "up"
        elif parsed_tgt.vcpus == parsed_cur.vcpus:
            action = "no_change"
            direction = "none"
    return VmSizingRecommendation(
        action=action,  # type: ignore[arg-type]
        current_sku=current_sku,
        suggested_sku=target_sku,
        current_family=parsed_cur.family if parsed_cur else "",
        suggested_family=parsed_tgt.family if parsed_tgt else None,
        family_label=parsed_tgt.family_label if parsed_tgt else "General purpose",
        direction=direction,
        avg_cpu_pct=None,
        avg_memory_pct=None,
        confidence=confidence,
        reasons=reasons,
    )


def align_vm_target_sku(
    engine_sizing: VmSizingRecommendation | None,
    *,
    current_sku: str,
    advisor: AdvisorVmTarget | None,
) -> tuple[VmSizingRecommendation | None, dict[str, Any]]:
    """Align target SKU with Advisor without computing savings (for inline analysis paths)."""
    decision = resolve_vm_cost_decision(
        vm={"location": ""},
        current_sku=current_sku,
        engine_sizing=engine_sizing,
        advisor=advisor,
        monthly_cost=0.0,
    )
    if decision is None:
        return engine_sizing, {}
    meta = decision.evidence()
    if advisor:
        meta["advisor_recommendation_id"] = advisor.recommendation_id
    return decision.sizing, meta


def compute_vm_resize_pricing(
    vm: dict,
    current_sku: str,
    target_sku: str,
    *,
    monthly_cost: float = 0.0,
) -> tuple[float, dict[str, Any]]:
    """Run-rate (or retail) savings for a SKU pair — independent of Advisor amounts."""
    mtd = monthly_cost if monthly_cost > 0 else None
    run_rate = project_mtd_to_monthly_run_rate(monthly_cost) if mtd else None
    pricing = enrich_pricing_payload(
        estimate_vm_sku_savings(
            (vm.get("location") or "").strip(),
            current_sku,
            target_sku,
            os_type=vm_os_type(vm),
            actual_monthly_cost=mtd,
            monthly_run_rate_usd=run_rate,
        )
    )
    savings = savings_from_retail_or_none(pricing)
    return (savings if savings is not None else 0.0), pricing


def resolve_vm_cost_decision(
    *,
    vm: dict,
    current_sku: str,
    engine_sizing: VmSizingRecommendation | None,
    advisor: AdvisorVmTarget | None,
    monthly_cost: float = 0.0,
    prefer_decommission: bool = False,
    decommission_savings: float = 0.0,
) -> VmCostDecision | None:
    """Pick action + target SKU (Advisor > engine) and compute savings from engine pricing."""
    if prefer_decommission and decommission_savings > 0:
        run_rate = project_mtd_to_monthly_run_rate(monthly_cost) if monthly_cost > 0 else decommission_savings
        return VmCostDecision(
            action="decommission",
            current_sku=current_sku,
            target_sku=None,
            sku_source="engine",
            engine_target_sku=None,
            advisor_target_sku=advisor.target_sku if advisor else None,
            sku_agreement="none",
            monthly_savings=round(max(decommission_savings, run_rate), 2),
            advisor_savings_reference=advisor.potential_savings_monthly if advisor else None,
            reasons=["Decommission supersedes rightsize on this resource."],
        )

    engine_target = (
        engine_sizing.suggested_sku
        if engine_sizing and engine_sizing.suggested_sku
        and engine_sizing.action in {"downgrade", "upgrade", "cross_family"}
        else None
    )
    advisor_target = advisor.target_sku if advisor and advisor.target_sku else None
    if advisor_target and advisor_target.lower() == current_sku.lower():
        advisor_target = None

    agreement = _sku_agreement(engine_target, advisor_target)
    if advisor_target:
        target_sku = advisor_target
        sku_source: SkuSource = "azure_advisor"
        reasons = list(engine_sizing.reasons if engine_sizing else [])
        if agreement == "agree":
            reasons.append("Engine agrees with Azure Advisor target SKU.")
        elif agreement == "disagree":
            reasons.append("Using Azure Advisor target SKU; engine suggested a different size.")
        else:
            reasons.append("Target SKU from Azure Advisor cost recommendation.")
        confidence = max(engine_sizing.confidence if engine_sizing else 0, 78)
        sizing = _sizing_from_target(current_sku, target_sku, reasons=reasons, confidence=confidence)
    elif engine_target:
        target_sku = engine_target
        sku_source = "engine"
        sizing = engine_sizing
        reasons = list(engine_sizing.reasons if engine_sizing else [])
    else:
        return None

    if not sizing or sizing.action not in {"downgrade", "upgrade", "cross_family"}:
        return None

    aligned_savings, aligned_pricing = compute_vm_resize_pricing(
        vm, current_sku, target_sku, monthly_cost=monthly_cost,
    )
    engine_savings = 0.0
    engine_pricing: dict[str, Any] = {}
    if engine_target and engine_target.lower() != target_sku.lower():
        engine_savings, engine_pricing = compute_vm_resize_pricing(
            vm, current_sku, engine_target, monthly_cost=monthly_cost,
        )

    monthly_savings = aligned_savings
    if monthly_savings <= 0 and engine_savings > 0:
        monthly_savings = engine_savings
        aligned_pricing = {
            **engine_pricing,
            "savings_fallback": "engine_target_sku",
            "savings_fallback_reason": "Advisor target SKU pricing unavailable; using engine SKU savings.",
        }

    advisor_ref = advisor.potential_savings_monthly if advisor else None
    if monthly_savings <= 0 and advisor_ref and advisor_ref > 0:
        monthly_savings = round(float(advisor_ref), 2)
        aligned_pricing = {
            **aligned_pricing,
            "savings_fallback": "advisor_reference",
            "savings_fallback_reason": "Using Azure Advisor reference savings; engine pricing unavailable.",
            "savings_source": "advisor_reference",
        }

    return VmCostDecision(
        action="rightsize",
        current_sku=current_sku,
        target_sku=target_sku,
        sku_source=sku_source,
        engine_target_sku=engine_target,
        advisor_target_sku=advisor_target,
        sku_agreement=agreement,
        monthly_savings=round(monthly_savings, 2),
        pricing=aligned_pricing,
        advisor_savings_reference=advisor_ref,
        sizing=sizing,
        reasons=reasons,
    )
