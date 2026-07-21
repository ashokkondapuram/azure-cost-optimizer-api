"""Tests for container registry optimization analysis."""

from app.optimizer.extended_engine import ExtendedOptimizationEngine
from app.optimizer.resource_engines.containers.acr.analysis import analyze_acr


def _registry(
    *,
    sku: str = "Premium",
    env: str = "dev",
    pulls: float = 100.0,
    storage_gb: float = 10.0,
    pushes: float = 20.0,
    reps: int = 0,
    retention_enabled: bool = False,
    private_endpoints: int = 0,
) -> dict:
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.ContainerRegistry/registries/acr-dev"
    props = {
        "policies": {
            "retentionPolicy": {
                "status": "enabled" if retention_enabled else "disabled",
                "days": 7,
            },
        },
        "zoneRedundancy": "Disabled",
    }
    if reps:
        props["_replications"] = [{"location": "westus"} for _ in range(reps)]
        props["replicationCount"] = reps
    if private_endpoints:
        props["privateEndpointConnections"] = [{"id": f"pe{i}"} for i in range(private_endpoints)]
    reg = {
        "id": rid,
        "name": "acr-dev",
        "sku": {"name": sku},
        "tags": {"environment": env},
        "properties": props,
        "_technical_facts": {
            "pull_count": pulls,
            "push_count": pushes,
            "storage_used_bytes": storage_gb * (1024 ** 3),
            "monitor_facts_status": "available",
            "data_source": "azure_monitor",
        },
    }
    return reg


def test_premium_extended_finds_low_pull_nonprod_registry():
    eng = ExtendedOptimizationEngine()
    reg = _registry(sku="Premium", pulls=80.0)
    rid = reg["id"].lower()
    findings = analyze_acr(eng, "sub", [reg], {rid: 40.0})
    assert len(findings) == 1
    assert findings[0].rule_id == "ACR_PREMIUM_EXTENDED"
    assert findings[0].estimated_savings_usd > 0


def test_premium_extended_skips_when_geo_replication_blocks_downgrade():
    eng = ExtendedOptimizationEngine()
    reg = _registry(sku="Premium", pulls=80.0, reps=1)
    rid = reg["id"].lower()
    findings = analyze_acr(eng, "sub", [reg], {rid: 40.0})
    assert not any(f.rule_id == "ACR_PREMIUM_EXTENDED" for f in findings)
    assert any(f.rule_id == "ACR_GEO_REPLICATION_EXTENDED" for f in findings)


def test_premium_extended_skips_prod_environment():
    eng = ExtendedOptimizationEngine()
    reg = _registry(sku="Premium", env="production", pulls=80.0)
    rid = reg["id"].lower()
    assert analyze_acr(eng, "sub", [reg], {rid: 40.0}) == []


def test_standard_extended_finds_idle_standard_registry():
    eng = ExtendedOptimizationEngine()
    reg = _registry(sku="Standard", pulls=50.0, storage_gb=20.0)
    rid = reg["id"].lower()
    findings = analyze_acr(eng, "sub", [reg], {rid: 25.0})
    assert any(f.rule_id == "ACR_STANDARD_EXTENDED" for f in findings)


def test_geo_replication_extended_fires_with_synced_replications():
    eng = ExtendedOptimizationEngine()
    reg = _registry(sku="Premium", reps=2, env="production", pulls=5000.0)
    rid = reg["id"].lower()
    findings = analyze_acr(eng, "sub", [reg], {rid: 80.0})
    geo = [f for f in findings if f.rule_id == "ACR_GEO_REPLICATION_EXTENDED"]
    assert len(geo) == 1
    assert geo[0].evidence["replication_count"] == 2


def test_storage_high_extended_finds_high_storage_low_activity():
    eng = ExtendedOptimizationEngine()
    reg = _registry(sku="Standard", pulls=50.0, storage_gb=80.0, pushes=10.0)
    rid = reg["id"].lower()
    findings = analyze_acr(eng, "sub", [reg], {rid: 30.0})
    assert any(f.rule_id == "ACR_STORAGE_HIGH_EXTENDED" for f in findings)


def test_retention_disabled_extended_on_premium_high_storage():
    eng = ExtendedOptimizationEngine()
    reg = _registry(sku="Premium", storage_gb=70.0, retention_enabled=False, env="production", pulls=5000.0)
    rid = reg["id"].lower()
    findings = analyze_acr(eng, "sub", [reg], {rid: 60.0})
    assert any(f.rule_id == "ACR_RETENTION_DISABLED_EXTENDED" for f in findings)


def test_acr_sub_engine_runs_in_extended_batch():
    eng = ExtendedOptimizationEngine()
    reg = _registry(sku="Premium", pulls=80.0)
    rid = reg["id"].lower()
    result = eng.analyze(
        subscription_id="sub",
        container_registries=[reg],
        cost_by_resource={rid: 40.0},
        resource_facts={
            rid: {
                "pull_count": 80.0,
                "push_count": 20.0,
                "storage_used_bytes": 10 * (1024 ** 3),
            },
        },
    )
    acr_findings = [f for f in result["findings"] if (f.get("resource_id") or "").lower() == rid]
    assert acr_findings
    assert any(f["rule_id"] == "ACR_PREMIUM_EXTENDED" for f in acr_findings)
