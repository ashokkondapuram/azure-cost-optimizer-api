"""SQL Database optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.azure_retail_pricing import estimate_service_tier_savings
from app.cost_utils import resource_cost
from app.pricing.savings_calculator import savings_from_retail_or_none
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import cpu_pct
from app.resource_utilization import is_low_cpu
from app.resource_utilization import make_check
from app.resource_utilization import monitor_facts_status
from app.resource_utilization import structured_evidence
from app.resource_utilization import utilization_gate


def analyze_sql(
    engine,
    subscription_id: str,
    sql_databases: list[dict],
    cost_by_resource: dict[str, float] | None = None,
) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    rule = engine.rules["SQL_SERVERLESS_EXTENDED"]
    idle_rule = engine.rules.get("SQL_IDLE_EXTENDED")
    for db in sql_databases:
        sku = db.get("sku") or {}
        tier = sku.get("tier") or ""
        name = db.get("name") or ""

        if idle_rule and idle_rule.enabled and tier in {"GeneralPurpose", "Standard", "BusinessCritical"}:
            if "serverless" not in str(sku.get("name") or "").lower():
                cpu = cpu_pct(db)
                if cpu is not None and cpu < idle_rule.db_dtu_idle_pct:
                    out.append(engine._finding(
                        rule=idle_rule,
                        subscription_id=subscription_id,
                        resource=db,
                        detail=f"SQL database '{name}' shows sustained low CPU ({cpu:.1f}%) on provisioned tier.",
                        recommendation="Pause, downsize, or move to serverless tier for intermittent workloads.",
                        savings=0,
                        waste_score=55,
                        confidence=confidence_with_monitor(70, db, boost=10),
                        priority="P2",
                        impact="Reduces idle database compute spend",
                        evidence=structured_evidence(
                            db,
                            determination="idle_database",
                            summary="Provisioned SQL database shows sustained low CPU.",
                            checks=[make_check("Average CPU", cpu, f"< {idle_rule.db_dtu_idle_pct}%", passed=True)],
                            extra={"sku": sku, "tier": tier},
                        ),
                    ))

        if not rule.enabled:
            continue
        if tier not in {"GeneralPurpose", "Standard", "BusinessCritical"}:
            continue
        if "serverless" in str(sku.get("name") or "").lower():
            continue

        facts_status = monitor_facts_status(db, "cpu_pct")
        if facts_status in {"missing", "partial"}:
            continue
        if not utilization_gate(db, "cpu_pct", allow_inventory_only=False):
            continue

        low_cpu = is_low_cpu(db, threshold=30.0)
        if low_cpu is False:
            continue
        if low_cpu is not True:
            continue

        cpu = cpu_pct(db)
        detail = f"SQL database '{name}' is provisioned and should be reviewed for serverless eligibility."
        if cpu is not None:
            detail += f" CPU utilization averages {cpu:.1f}% in Azure Monitor."
        monthly = resource_cost(cost_by_resource or {}, db.get("id", ""))
        pricing = estimate_service_tier_savings(
            db.get("location") or "",
            "SQL Database",
            str(sku.get("name") or tier),
            "serverless",
            cache_prefix="sql",
            actual_monthly_cost=monthly if monthly > 0 else None,
        )
        savings = savings_from_retail_or_none(pricing) or 0.0

        out.append(engine._finding(
            rule=rule,
            subscription_id=subscription_id,
            resource=db,
            detail=detail,
            recommendation="Move dev/test and intermittent workloads to serverless compute with auto-pause where supported.",
            savings=savings,
            waste_score=52,
            confidence=confidence_with_monitor(66, db, boost=16),
            priority="P3",
            impact="Can reduce idle database compute spend",
            evidence=structured_evidence(
                db,
                determination="serverless_candidate",
                summary="Provisioned SQL database shows sustained low CPU in Azure Monitor.",
                checks=[
                    make_check("Average CPU", cpu, "< 30%", passed=True),
                ],
                extra={"sku": sku, **pricing},
            ),
        ))
    return out
