"""PostgreSQL optimization analysis rules."""
from __future__ import annotations

from typing import Any

from app.optimizer.core.finding import ExtendedFinding
from app.cost_utils import resource_cost
from app.cost_utils import savings_from_factor
from app.azure_retail_pricing import estimate_postgresql_tier_savings
from app.pricing.savings_calculator import savings_from_retail_or_none
from app.resource_utilization import confidence_with_monitor
from app.resource_utilization import cpu_pct
from app.resource_utilization import fact_value
from app.resource_utilization import is_low_cpu
from app.resource_utilization import make_check
from app.resource_utilization import metrics_block_rightsize
from app.resource_utilization import monitor_facts_status
from app.resource_utilization import structured_evidence
from app.resource_utilization import utilization_gate


def analyze_postgresql(engine, subscription_id: str, servers: list[dict], cost_by_resource: dict[str, float]) -> list[ExtendedFinding]:
    out: list[ExtendedFinding] = []
    stopped_rule = engine.rules.get("POSTGRESQL_STOPPED_EXTENDED")
    burstable_rule = engine.rules.get("POSTGRESQL_BURSTABLE_EXTENDED")
    storage_rule = engine.rules.get("POSTGRESQL_STORAGE_EXTENDED")

    for server in servers:
        props = server.get("properties") or {}
        sku = server.get("sku") or {}
        sku_name = (sku.get("name") or "").lower()
        tier = (sku.get("tier") or "").lower()
        state = (props.get("state") or "").lower()
        name = server.get("name") or ""
        tags = server.get("tags") or {}
        env = str(tags.get("environment") or tags.get("env") or "").lower()
        monthly = resource_cost(cost_by_resource, server.get("id", ""))
        storage_gb = int(props.get("storage", {}).get("storageSizeGB") or 0)

        if stopped_rule and stopped_rule.enabled and state == "stopped":
            out.append(engine._finding(
                rule=stopped_rule,
                subscription_id=subscription_id,
                resource=server,
                detail=f"PostgreSQL server '{name}' is stopped but may still incur storage and backup charges.",
                recommendation="Export data and delete the server if no longer needed, or start it during required windows only.",
                savings=savings_from_factor(monthly, 0.6) if monthly > 0 else 0,
                waste_score=58,
                confidence=80,
                priority="P2",
                impact="Eliminates idle database storage and backup cost",
                evidence={"state": state, "storage_gb": storage_gb},
            ))

        if burstable_rule and burstable_rule.enabled and env in burstable_rule.nonprod_tag_values:
            if tier in ("generalpurpose", "memoryoptimized") or sku_name.startswith(("gp", "mo")):
                if metrics_block_rightsize(server):
                    continue
                facts_status = monitor_facts_status(server, "cpu_pct")
                if facts_status in {"missing", "partial"}:
                    continue
                if not utilization_gate(server, "cpu_pct", allow_inventory_only=False):
                    continue
                low_cpu = is_low_cpu(server, threshold=35.0)
                if low_cpu is not True:
                    continue
                cpu = cpu_pct(server)
                detail = f"PostgreSQL '{name}' uses {tier or sku_name} SKU in a non-production environment."
                if cpu is not None:
                    detail += f" CPU averages {cpu:.1f}% in Azure Monitor."
                pricing = estimate_postgresql_tier_savings(
                    server.get("location") or "",
                    sku_name or tier,
                    "Standard_B2s",
                    actual_monthly_cost=monthly if monthly > 0 else None,
                )
                savings = savings_from_retail_or_none(pricing)
                if savings is None and monthly > 0:
                    savings = savings_from_factor(monthly, 0.45)
                out.append(engine._finding(
                    rule=burstable_rule,
                    subscription_id=subscription_id,
                    resource=server,
                    detail=detail,
                    recommendation="Move dev/test workloads to Burstable (B-series) compute to reduce baseline cost.",
                    savings=savings or 0,
                    waste_score=56,
                    confidence=confidence_with_monitor(74, server, boost=14),
                    priority="P2",
                    impact="Database compute right-sizing for non-prod",
                    evidence=structured_evidence(
                        server,
                        determination="burstable_candidate",
                        summary="Non-production PostgreSQL server shows low CPU in Azure Monitor.",
                        checks=[make_check("Average CPU", cpu, "< 35%", passed=True)],
                        extra={"sku": sku_name, "tier": tier, "environment": env, **pricing},
                    ),
                ))

        if storage_rule and storage_rule.enabled:
            storage_pct = fact_value(server, "storage_pct")
            facts_status = monitor_facts_status(server, "storage_pct")
            over_provisioned = storage_gb >= 256
            low_utilization = storage_pct is not None and storage_pct < 40.0
            if not over_provisioned and not low_utilization:
                continue
            if facts_status in {"missing", "partial"} and storage_pct is not None:
                continue
            detail = f"PostgreSQL '{name}' has {storage_gb} GB provisioned storage."
            if low_utilization:
                detail += f" Storage utilization averages {storage_pct:.1f}% in Azure Monitor."
            out.append(engine._finding(
                rule=storage_rule,
                subscription_id=subscription_id,
                resource=server,
                detail=detail,
                recommendation="Review actual data size and enable storage auto-grow with a right-sized cap.",
                savings=savings_from_factor(monthly, 0.2) if monthly > 0 else 0,
                waste_score=44 if low_utilization else 40,
                confidence=confidence_with_monitor(60, server, boost=12 if low_utilization else 0),
                priority="P3",
                impact="Storage provisioning optimization",
                evidence=structured_evidence(
                    server,
                    determination="storage_overprovisioned",
                    summary="PostgreSQL storage is over-provisioned relative to monitored utilization.",
                    checks=[
                        make_check("Provisioned storage (GB)", storage_gb, "≥ 256", passed=over_provisioned),
                        make_check("Storage utilization", storage_pct, "< 40%", passed=low_utilization),
                    ],
                    extra={"storage_gb": storage_gb},
                ),
            ))
    return out
