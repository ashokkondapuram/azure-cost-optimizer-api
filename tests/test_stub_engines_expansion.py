"""Tests for expanded stub resource optimization engines."""

from __future__ import annotations

from datetime import datetime, timezone

from app.optimizer.advanced_rules import ADVANCED_RULES
from app.optimizer.core.finding import ExtendedFinding
from app.service_thresholds import load_service_specifications, optimization_thresholds
from it_services.analytics_adx.engine.analysis import analyze_adx
from it_services.analytics_adx.engine.optimization_rules import evaluate_adx_low_ingestion
from it_services.analytics_databricks.engine.analysis import analyze_databricks
from it_services.analytics_databricks.engine.optimization_rules import evaluate_databricks_dev_workspace
from it_services.backup_recoveryvault.engine.analysis import analyze_recovery_vaults
from it_services.integration_apim.engine.analysis import analyze_apim
from it_services.integration_datafactory.engine.optimization_rules import evaluate_datafactory_idle_pipelines
from it_services.messaging_eventhub.engine.analysis import analyze_event_hubs
from it_services.messaging_servicebus.engine.optimization_rules import evaluate_servicebus_idle_namespace
from it_services.monitoring_loganalytics.engine.optimization_rules import evaluate_log_analytics_high_ingestion
from it_services.network_frontdoor.engine.analysis import analyze_front_doors
from it_services.search_cognitivesearch.engine.optimization_rules import evaluate_search_over_replicas


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
            resource_type=resource.get("type") or "",
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


def _resource(
    *,
    name: str,
    rtype: str,
    facts: dict | None = None,
    tags: dict | None = None,
    props: dict | None = None,
    sku: dict | None = None,
) -> dict:
    row = {
        "id": f"/subscriptions/s/resourceGroups/rg/providers/{rtype}/{name}",
        "name": name,
        "type": rtype,
        "location": "eastus",
        "properties": props or {},
        "sku": sku or {},
        "tags": tags or {},
    }
    if facts:
        row["_technical_facts"] = {**facts, "data_source": "azure_monitor"}
    return row


def test_threshold_json_files_load():
    for canonical in (
        "analytics/databricks",
        "analytics/synapse",
        "analytics/adx",
        "messaging/eventhub",
        "monitoring/loganalytics",
        "network/frontdoor",
    ):
        specs = load_service_specifications(canonical)
        assert specs.get("schema_version") == 1
        th = optimization_thresholds(canonical)
        assert th.get("min_monthly_cost_usd", 0) > 0


def test_databricks_dev_workspace_rule():
    ws = _resource(
        name="dbw-dev",
        rtype="Microsoft.Databricks/workspaces",
        tags={"environment": "dev"},
    )
    draft = evaluate_databricks_dev_workspace(
        ws, 200.0, ADVANCED_RULES["DATABRICKS_DEV_WORKSPACE_EXTENDED"],
    )
    assert draft is not None
    assert draft.rule_id == "DATABRICKS_DEV_WORKSPACE_EXTENDED"


def test_analyze_databricks_integration():
    engine = _FakeEngine()
    ws = _resource(name="dbw1", rtype="Microsoft.Databricks/workspaces")
    findings = analyze_databricks(engine, "sub", [ws], {ws["id"].lower(): 250.0})
    assert any(f.rule_id == "DATABRICKS_CLUSTER_EXTENDED" for f in findings)


def test_adx_low_ingestion_rule():
    cluster = _resource(
        name="adx1",
        rtype="Microsoft.Kusto/clusters",
        facts={"ingestion_bytes": 100.0},
    )
    draft = evaluate_adx_low_ingestion(cluster, 150.0, ADVANCED_RULES["ADX_LOW_INGESTION_EXTENDED"])
    assert draft is not None
    assert "100.0 MB" in draft.detail or "100.0" in draft.detail


def test_analyze_adx_integration():
    engine = _FakeEngine()
    cluster = _resource(
        name="adx1",
        rtype="Microsoft.Kusto/clusters",
        facts={"ingestion_bytes": 50.0},
    )
    findings = analyze_adx(engine, "sub", [cluster], {cluster["id"].lower(): 180.0})
    rule_ids = {f.rule_id for f in findings}
    assert "ADX_INGESTION_EXTENDED" in rule_ids
    assert "ADX_LOW_INGESTION_EXTENDED" in rule_ids


def test_datafactory_idle_pipelines():
    factory = _resource(
        name="adf1",
        rtype="Microsoft.DataFactory/factories",
        facts={"pipeline_succeeded": 2.0},
    )
    draft = evaluate_datafactory_idle_pipelines(
        factory, 120.0, ADVANCED_RULES["DATA_FACTORY_IDLE_PIPELINES_EXTENDED"],
    )
    assert draft is not None


def test_servicebus_idle_namespace_uses_active_messages():
    ns = _resource(
        name="sb1",
        rtype="Microsoft.ServiceBus/namespaces",
        sku={"name": "Premium"},
        facts={"active_messages": 5.0},
    )
    draft = evaluate_servicebus_idle_namespace(
        ns, 90.0, ADVANCED_RULES["SERVICE_BUS_IDLE_NAMESPACE_EXTENDED"],
    )
    assert draft is not None


def test_log_analytics_high_ingestion():
    ws = _resource(
        name="law1",
        rtype="Microsoft.OperationalInsights/workspaces",
        props={"retentionInDays": 30},
        facts={"ingestion_gb": 25.0},
    )
    draft = evaluate_log_analytics_high_ingestion(
        ws, 200.0, ADVANCED_RULES["LOG_ANALYTICS_INGESTION_EXTENDED"],
    )
    assert draft is not None


def test_search_over_replicas():
    svc = _resource(
        name="search1",
        rtype="Microsoft.Search/searchServices",
        props={"replicaCount": 3, "partitionCount": 1},
        facts={"search_qps": 2.0},
    )
    draft = evaluate_search_over_replicas(
        svc, 150.0, ADVANCED_RULES["COGNITIVE_SEARCH_REPLICA_EXTENDED"],
    )
    assert draft is not None


def test_analyze_front_doors():
    engine = _FakeEngine()
    profile = _resource(
        name="fd1",
        rtype="Microsoft.Network/frontdoors",
        facts={"request_count": 100.0},
    )
    findings = analyze_front_doors(engine, "sub", [profile], {profile["id"].lower(): 120.0})
    rule_ids = {f.rule_id for f in findings}
    assert "NETWORK_FRONT_DOOR_COST_EXTENDED" in rule_ids
    assert "NETWORK_FRONT_DOOR_IDLE_EXTENDED" in rule_ids


def test_analyze_event_hubs_with_metrics():
    engine = _FakeEngine()
    ns = _resource(
        name="eh1",
        rtype="Microsoft.EventHub/namespaces",
        sku={"tier": "Standard"},
        facts={"incoming_messages": 100.0, "outgoing_messages": 50.0},
    )
    findings = analyze_event_hubs(engine, "sub", [ns], {ns["id"].lower(): 90.0})
    assert any(f.rule_id == "EVENT_HUBS_TIER_EXTENDED" for f in findings)


def test_analyze_apim_with_low_requests():
    engine = _FakeEngine()
    svc = _resource(
        name="apim1",
        rtype="Microsoft.ApiManagement/service",
        sku={"name": "Standard", "capacity": 2},
        facts={"request_count": 500.0, "capacity_pct": 10.0},
    )
    findings = analyze_apim(engine, "sub", [svc], {svc["id"].lower(): 250.0})
    rule_ids = {f.rule_id for f in findings}
    assert "APIM_SKU_EXTENDED" in rule_ids
    assert "APIM_LOW_TRAFFIC_EXTENDED" in rule_ids


def test_analyze_recovery_vault_growth():
    engine = _FakeEngine()
    vault = _resource(name="rsv1", rtype="Microsoft.RecoveryServices/vaults")
    findings = analyze_recovery_vaults(engine, "sub", [vault], {vault["id"].lower(): 200.0})
    rule_ids = {f.rule_id for f in findings}
    assert "BACKUP_RETENTION_EXTENDED" in rule_ids
    assert "BACKUP_VAULT_GROWTH_EXTENDED" in rule_ids
