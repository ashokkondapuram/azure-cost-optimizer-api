"""Tests for PostgreSQL flexible server optimization engine."""

from __future__ import annotations

from app.optimizer.advanced_rules import ADVANCED_RULES
from app.optimizer.resource_engines.database.postgresql.analysis import analyze_postgresql
from app.optimizer.resource_engines.database.postgresql.optimization_rules import (
    evaluate_postgresql_burstable,
    evaluate_postgresql_connection_pool_risk,
    evaluate_postgresql_ha_required,
    evaluate_postgresql_ha_unnecessary,
    evaluate_postgresql_high_compute,
    evaluate_postgresql_low_compute,
    evaluate_postgresql_memory_pressure,
    evaluate_postgresql_read_replica,
    evaluate_postgresql_stopped,
    evaluate_postgresql_storage_expansion,
    evaluate_postgresql_version_outdated,
)
from app.postgresql_sku_catalog import load_postgresql_sku_specifications, parse_postgresql_arm_server


class _FakeEngine:
    def __init__(self):
        self.rules = ADVANCED_RULES

    def _extract_rg(self, rid: str) -> str:
        parts = (rid or "").split("/")
        if "resourceGroups" in parts:
            idx = parts.index("resourceGroups")
            return parts[idx + 1] if idx + 1 < len(parts) else ""
        return ""

    def _finding(self, **kwargs):
        from datetime import datetime, timezone
        from app.optimizer.core.finding import ExtendedFinding

        rule = kwargs.pop("rule")
        resource = kwargs.get("resource") or {}
        rid = resource.get("id") or ""
        savings = float(kwargs.get("savings", 0) or 0)
        return ExtendedFinding(
            rule_id=rule.id,
            rule_name=rule.name,
            category=rule.category.value,
            severity=rule.severity.value,
            subscription_id=kwargs.get("subscription_id", ""),
            resource_id=rid,
            resource_name=resource.get("name") or "",
            resource_type=resource.get("type") or "database/postgresql",
            resource_group=self._extract_rg(rid),
            location=resource.get("location") or "",
            detail=kwargs.get("detail", ""),
            recommendation=kwargs.get("recommendation", ""),
            estimated_savings_usd=round(savings, 2),
            annualized_savings_usd=round(savings * 12, 2),
            waste_score=kwargs.get("waste_score", 0),
            confidence_score=kwargs.get("confidence", 0),
            action_priority=kwargs.get("priority", "P3"),
            impact=kwargs.get("impact", ""),
            evidence=kwargs.get("evidence") or {},
            tags=resource.get("tags") or {},
            detected_at=datetime.now(timezone.utc).isoformat(),
        )


def _server(
    *,
    name: str = "pg1",
    sku: str = "Standard_D4s_v3",
    tier: str = "GeneralPurpose",
    tags: dict | None = None,
    facts: dict | None = None,
    state: str = "Ready",
    ha_mode: str = "Disabled",
    version: str = "14",
    storage_gb: int = 128,
    backup_days: int = 7,
    source_server_id: str | None = None,
) -> dict:
    props = {
        "state": state,
        "version": version,
        "storage": {"storageSizeGB": storage_gb},
        "highAvailability": {"mode": ha_mode},
        "backup": {"retentionDays": backup_days, "geoRedundantBackup": "Disabled"},
    }
    if source_server_id:
        props["sourceServerResourceId"] = source_server_id
    row = {
        "id": f"/subscriptions/s/resourceGroups/rg/providers/Microsoft.DBforPostgreSQL/flexibleServers/{name}",
        "name": name,
        "location": "canadacentral",
        "sku": {"name": sku, "tier": tier},
        "properties": props,
        "tags": tags or {},
    }
    if facts:
        row["_technical_facts"] = {**facts, "data_source": "azure_monitor"}
    return row


def test_postgresql_sku_specifications_loads():
    specs = load_postgresql_sku_specifications()
    assert specs.get("schema_version") == 1
    assert "Burstable" in specs.get("tiers", {})
    assert "GeneralPurpose" in specs.get("tiers", {})


def test_parse_postgresql_arm_server():
    ctx = parse_postgresql_arm_server(_server(sku="Standard_D4s_v3", ha_mode="SameZone", version="14"))
    assert ctx["tier"] == "GeneralPurpose"
    assert ctx["vcores"] == 4
    assert ctx["ha_enabled"] is True
    assert ctx["ha_mode"] == "SameZone"


def test_stopped_server_finding():
    server = _server(state="Stopped")
    ctx = parse_postgresql_arm_server(server)
    draft = evaluate_postgresql_stopped(server, ctx, 100.0, ADVANCED_RULES["POSTGRESQL_STOPPED_EXTENDED"])
    assert draft is not None
    assert draft.rule_id == "POSTGRESQL_STOPPED_EXTENDED"
    assert draft.savings == 60.0


def test_burstable_nonprod_low_cpu():
    server = _server(
        tags={"environment": "dev"},
        facts={"cpu_pct": 20.0, "memory_pct": 30.0},
    )
    ctx = parse_postgresql_arm_server(server)
    draft = evaluate_postgresql_burstable(server, ctx, 200.0, ADVANCED_RULES["POSTGRESQL_BURSTABLE_EXTENDED"])
    assert draft is not None
    assert draft.rule_id == "POSTGRESQL_BURSTABLE_EXTENDED"


def test_low_compute_utilization():
    server = _server(
        sku="Standard_D8s_v3",
        facts={"cpu_pct": 18.0, "memory_pct": 25.0},
    )
    ctx = parse_postgresql_arm_server(server)
    draft = evaluate_postgresql_low_compute(server, ctx, 300.0, ADVANCED_RULES["POSTGRESQL_LOW_COMPUTE_UTILIZATION"])
    assert draft is not None
    assert draft.rule_id == "POSTGRESQL_LOW_COMPUTE_UTILIZATION"
    assert "Standard_D4s_v3" in draft.recommendation


def test_high_compute_demand():
    server = _server(facts={"cpu_pct": 92.0})
    ctx = parse_postgresql_arm_server(server)
    draft = evaluate_postgresql_high_compute(server, ctx, 250.0, ADVANCED_RULES["POSTGRESQL_HIGH_COMPUTE_DEMAND"])
    assert draft is not None
    assert draft.rule_id == "POSTGRESQL_HIGH_COMPUTE_DEMAND"
    assert draft.savings == 0.0


def test_memory_pressure():
    server = _server(facts={"memory_pct": 91.0})
    ctx = parse_postgresql_arm_server(server)
    draft = evaluate_postgresql_memory_pressure(server, ctx, 250.0, ADVANCED_RULES["POSTGRESQL_MEMORY_PRESSURE"])
    assert draft is not None
    assert draft.priority == "P1"


def test_storage_expansion():
    server = _server(storage_gb=512, facts={"storage_pct": 88.0})
    ctx = parse_postgresql_arm_server(server)
    draft = evaluate_postgresql_storage_expansion(server, ctx, 100.0, ADVANCED_RULES["POSTGRESQL_STORAGE_EXPANSION"])
    assert draft is not None
    assert draft.rule_id == "POSTGRESQL_STORAGE_EXPANSION"


def test_connection_pool_risk():
    server = _server(facts={"active_connections": 4000.0})
    ctx = parse_postgresql_arm_server(server)
    draft = evaluate_postgresql_connection_pool_risk(
        server, ctx, 100.0, ADVANCED_RULES["POSTGRESQL_CONNECTION_POOL_RISK"],
    )
    assert draft is not None
    assert "PgBouncer" in draft.recommendation


def test_ha_unnecessary_nonprod():
    server = _server(tags={"environment": "dev"}, ha_mode="SameZone")
    ctx = parse_postgresql_arm_server(server)
    draft = evaluate_postgresql_ha_unnecessary(server, ctx, 300.0, ADVANCED_RULES["POSTGRESQL_HA_UNNECESSARY"])
    assert draft is not None
    assert draft.savings == 100.0


def test_ha_required_prod():
    server = _server(tags={"environment": "production"}, ha_mode="Disabled")
    ctx = parse_postgresql_arm_server(server)
    draft = evaluate_postgresql_ha_required(server, ctx, 400.0, ADVANCED_RULES["POSTGRESQL_HA_REQUIRED"])
    assert draft is not None
    assert draft.rule_id == "POSTGRESQL_HA_REQUIRED"


def test_read_replica_analysis():
    server = _server(
        name="replica1",
        source_server_id="/subscriptions/s/resourceGroups/rg/providers/Microsoft.DBforPostgreSQL/flexibleServers/pg1",
        facts={"replication_lag_sec": 12.0},
    )
    ctx = parse_postgresql_arm_server(server)
    draft = evaluate_postgresql_read_replica(server, ctx, 180.0, ADVANCED_RULES["POSTGRESQL_READ_REPLICA_ANALYSIS"])
    assert draft is not None
    assert "lag" in draft.detail.lower()


def test_version_outdated():
    server = _server(version="12")
    ctx = parse_postgresql_arm_server(server)
    draft = evaluate_postgresql_version_outdated(server, ctx, 100.0, ADVANCED_RULES["POSTGRESQL_VERSION_OUTDATED"])
    assert draft is not None
    assert draft.rule_id == "POSTGRESQL_VERSION_OUTDATED"


def test_analyze_postgresql_integration():
    engine = _FakeEngine()
    servers = [
        _server(state="Stopped"),
        _server(tags={"environment": "dev"}, facts={"cpu_pct": 15.0, "memory_pct": 20.0}),
        _server(facts={"cpu_pct": 90.0}),
    ]
    costs = {s["id"].lower(): 120.0 for s in servers}
    findings = analyze_postgresql(engine, "sub", servers, costs)
    rule_ids = {f.rule_id for f in findings}
    assert "POSTGRESQL_STOPPED_EXTENDED" in rule_ids
    assert "POSTGRESQL_BURSTABLE_EXTENDED" in rule_ids
    assert "POSTGRESQL_HIGH_COMPUTE_DEMAND" in rule_ids
