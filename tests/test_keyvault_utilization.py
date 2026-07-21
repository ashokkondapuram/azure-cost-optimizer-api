"""Tests for Key Vault utilization helpers."""

from app.keyvault_utilization import (
    blocks_premium_downgrade,
    is_high_keyvault_ops,
    is_idle_keyvault,
    kv_sku_name,
    meets_kv_savings_gate,
    protection_baseline_gap,
    purge_protection_enabled,
    soft_delete_enabled,
)


def _vault(*, sku: str = "standard", soft_delete: bool = True, purge: bool = True, hits: float | None = 5.0) -> dict:
    vault = {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.KeyVault/vaults/kv1",
        "name": "kv1",
        "sku": {"name": sku, "family": "A"},
        "properties": {
            "enableSoftDelete": soft_delete,
            "enablePurgeProtection": purge,
        },
    }
    if hits is not None:
        vault["_technical_facts"] = {"api_hits": hits}
    return vault


def test_kv_sku_name_normalizes():
    assert kv_sku_name(_vault(sku="premium")) == "premium"


def test_protection_baseline_gap_when_soft_delete_off():
    assert protection_baseline_gap(_vault(soft_delete=False)) is True


def test_protection_baseline_gap_when_protected():
    assert protection_baseline_gap(_vault()) is False


def test_is_idle_keyvault_below_threshold():
    assert is_idle_keyvault(_vault(hits=3.0), threshold=10) is True


def test_is_high_keyvault_ops_above_threshold():
    assert is_high_keyvault_ops(_vault(hits=60_000.0), threshold=50_000) is True


def test_blocks_premium_downgrade_for_production():
    vault = _vault(sku="premium", hits=2.0)
    vault["tags"] = {"environment": "production"}
    assert blocks_premium_downgrade(vault, nonprod_values=["dev", "test"]) is True


def test_meets_kv_savings_gate():
    assert meets_kv_savings_gate(12.0, min_monthly_savings_usd=5.0) is True
    assert meets_kv_savings_gate(1.0, min_monthly_savings_usd=5.0) is False


def test_soft_delete_and_purge_helpers():
    assert soft_delete_enabled(_vault(soft_delete=True)) is True
    assert purge_protection_enabled(_vault(purge=True)) is True
