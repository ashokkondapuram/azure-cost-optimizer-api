"""Tests for container registry utilization helpers."""

from app.acr_utilization import (
    acr_sku_name,
    blocks_acr_sku_downgrade,
    is_high_acr_storage,
    is_low_pull_volume,
    meets_acr_savings_gate,
    premium_features_in_use,
    replication_count,
    retention_policy_status,
)


def _registry(*, sku: str = "Premium", reps: int = 0, retention_enabled: bool = False) -> dict:
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
    return {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.ContainerRegistry/registries/acr1",
        "name": "acr1",
        "sku": {"name": sku},
        "properties": props,
    }


def test_acr_sku_name_normalizes():
    assert acr_sku_name(_registry(sku="Premium")) == "premium"


def test_replication_count_from_synced_children():
    assert replication_count(_registry(reps=2)) == 2


def test_premium_features_in_use_geo_replication():
    assert "geo_replication" in premium_features_in_use(_registry(reps=1))


def test_blocks_acr_sku_downgrade_with_geo_replication():
    assert blocks_acr_sku_downgrade(_registry(reps=1)) is True


def test_blocks_acr_sku_downgrade_when_clean():
    assert blocks_acr_sku_downgrade(_registry()) is False


def test_retention_policy_status():
    enabled, days = retention_policy_status(_registry(retention_enabled=True))
    assert enabled is True
    assert days == 7


def test_is_low_pull_volume_from_facts():
    reg = _registry()
    reg["_technical_facts"] = {"pull_count": 120.0}
    assert is_low_pull_volume(reg, threshold=500) is True


def test_is_high_acr_storage():
    reg = _registry()
    reg["_technical_facts"] = {"storage_used_bytes": 60 * (1024 ** 3)}
    assert is_high_acr_storage(reg, min_gb=50) is True


def test_meets_acr_savings_gate():
    assert meets_acr_savings_gate(10.0, min_monthly_savings_usd=5.0) is True
    assert meets_acr_savings_gate(2.0, min_monthly_savings_usd=5.0) is False
