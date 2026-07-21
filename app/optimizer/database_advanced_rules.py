"""Advanced database optimization rules (elastic pool, hybrid benefit, query performance)."""

from __future__ import annotations

from app.cost_utils import resource_cost
from app.optimizer.standard_finding import Finding


def _gc(engine):
    return getattr(engine, "global_config", None)


def analyze_database_advanced(
    engine,
    subscription_id: str,
    sql_databases: list[dict],
    cost_by_resource: dict[str, float] | None = None,
) -> list[Finding]:
    """Elastic pool consolidation, hybrid benefit, and query performance candidates."""
    out: list[Finding] = []
    gc = _gc(engine)
    pool_rule = engine.rules.get("SQL_ELASTIC_POOL_CANDIDATE")
    hybrid_rule = engine.rules.get("SQL_HYBRID_BENEFIT_CANDIDATE")
    query_rule = engine.rules.get("SQL_QUERY_PERF_REVIEW")

    by_server: dict[str, list[dict]] = {}
    for db in sql_databases:
        rid = (db.get("id") or "").lower()
        if "/servers/" not in rid or "/databases/" not in rid:
            continue
        server = rid.split("/servers/", 1)[-1].split("/")[0]
        by_server.setdefault(server, []).append(db)

    for server, dbs in by_server.items():
        if pool_rule and pool_rule.enabled and len(dbs) >= 3:
            total_cost = sum(resource_cost(cost_by_resource or {}, d.get("id", "")) for d in dbs)
            if total_cost >= getattr(pool_rule, "min_monthly_savings_usd", 5.0):
                out.append(Finding(
                    pool_rule,
                    dbs[0],
                    detail=f"SQL server '{server}' hosts {len(dbs)} databases that may consolidate into an elastic pool.",
                    recommendation="Review elastic pool SKU for shared DTU/vCore utilization.",
                    savings=round(total_cost * 0.15, 2),
                    score=58,
                    evidence={"server": server, "database_count": len(dbs), "combined_monthly_usd": total_cost},
                    global_config=gc,
                ))

        if hybrid_rule and hybrid_rule.enabled:
            for db in dbs:
                sku = db.get("sku") or {}
                tier = str(sku.get("tier") or "")
                if tier not in {"GeneralPurpose", "BusinessCritical"}:
                    continue
                monthly = resource_cost(cost_by_resource or {}, db.get("id", ""))
                if monthly < getattr(hybrid_rule, "min_monthly_savings_usd", 5.0):
                    continue
                out.append(Finding(
                    hybrid_rule,
                    db,
                    detail=f"SQL database '{db.get('name')}' may qualify for Azure Hybrid Benefit.",
                    recommendation="Apply AHUB licensing if you have eligible SQL Server licenses with Software Assurance.",
                    savings=round(monthly * 0.40, 2),
                    score=50,
                    evidence={"tier": tier, "monthly_cost_usd": monthly},
                    global_config=gc,
                ))

        if query_rule and query_rule.enabled:
            for db in dbs:
                props = db.get("properties") or {}
                sku = db.get("sku") or {}
                tier = str(sku.get("tier") or sku.get("name") or "")
                monthly = resource_cost(cost_by_resource or {}, db.get("id", ""))
                max_size = props.get("maxSizeBytes") or props.get("maxSize")
                if monthly < getattr(query_rule, "min_monthly_savings_usd", 10.0):
                    continue
                if tier and "serverless" in tier.lower():
                    continue
                out.append(Finding(
                    query_rule,
                    db,
                    detail=f"SQL database '{db.get('name')}' on tier '{tier}' — review query performance and indexing.",
                    recommendation="Enable Query Store, review top DTU/vCore consumers, and tune indexes or tier.",
                    savings=round(monthly * 0.12, 2),
                    score=46,
                    evidence={"tier": tier, "monthly_cost_usd": monthly, "max_size_bytes": max_size},
                    global_config=gc,
                ))
    return out
