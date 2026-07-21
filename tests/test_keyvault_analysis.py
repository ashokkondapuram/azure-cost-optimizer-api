"""Tests for Key Vault optimization analysis."""

from app.optimizer.extended_engine import ExtendedOptimizationEngine
from app.optimizer.resource_engines.security.keyvault.analysis import analyze_keyvaults


def _vault(
    *,
    sku: str = "standard",
    soft_delete: bool = True,
    purge: bool = True,
    hits: float = 5.0,
    env: str = "dev",
) -> dict:
    rid = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.KeyVault/vaults/kv-dev"
    return {
        "id": rid,
        "name": "kv-dev",
        "sku": {"name": sku, "family": "A"},
        "tags": {"environment": env},
        "properties": {
            "enableSoftDelete": soft_delete,
            "enablePurgeProtection": purge,
        },
        "_technical_facts": {
            "api_hits": hits,
            "monitor_facts_status": "available",
            "data_source": "azure_monitor",
        },
    }


def test_protection_extended_reports_baseline_gap():
    eng = ExtendedOptimizationEngine()
    vault = _vault(soft_delete=False, purge=False)
    findings = analyze_keyvaults(eng, "sub", [vault], {})
    assert len(findings) == 1
    assert findings[0].rule_id == "KEYVAULT_PROTECTION_EXTENDED"
    assert findings[0].estimated_savings_usd == 0


def test_idle_extended_uses_mtd_cost():
    eng = ExtendedOptimizationEngine()
    vault = _vault(hits=2.0)
    rid = vault["id"].lower()
    findings = analyze_keyvaults(eng, "sub", [vault], {rid: 18.0})
    idle = [f for f in findings if f.rule_id == "KEYVAULT_IDLE_EXTENDED"]
    assert len(idle) == 1
    assert idle[0].estimated_savings_usd == 18.0


def test_premium_extended_finds_nonprod_premium_vault():
    eng = ExtendedOptimizationEngine()
    vault = _vault(sku="premium", hits=2.0)
    rid = vault["id"].lower()
    findings = analyze_keyvaults(eng, "sub", [vault], {rid: 25.0})
    premium = [f for f in findings if f.rule_id == "KEYVAULT_PREMIUM_EXTENDED"]
    assert len(premium) == 1
    assert premium[0].estimated_savings_usd > 0


def test_premium_extended_skips_production():
    eng = ExtendedOptimizationEngine()
    vault = _vault(sku="premium", hits=2.0, env="production")
    rid = vault["id"].lower()
    findings = analyze_keyvaults(eng, "sub", [vault], {rid: 25.0})
    assert not any(f.rule_id == "KEYVAULT_PREMIUM_EXTENDED" for f in findings)


def test_high_ops_extended_fires_on_volume():
    eng = ExtendedOptimizationEngine()
    vault = _vault(hits=75_000.0)
    rid = vault["id"].lower()
    findings = analyze_keyvaults(eng, "sub", [vault], {rid: 40.0})
    high = [f for f in findings if f.rule_id == "KEYVAULT_HIGH_OPS_EXTENDED"]
    assert len(high) == 1


def test_keyvault_sub_engine_runs_in_extended_batch():
    eng = ExtendedOptimizationEngine()
    vault = _vault(hits=2.0)
    rid = vault["id"].lower()
    result = eng.analyze(
        subscription_id="sub",
        keyvaults=[vault],
        cost_by_resource={rid: 15.0},
        resource_facts={rid: {"api_hits": 2.0}},
    )
    kv_findings = [f for f in result["findings"] if (f.get("resource_id") or "").lower() == rid]
    assert kv_findings
    assert any(f["rule_id"] == "KEYVAULT_IDLE_EXTENDED" for f in kv_findings)
