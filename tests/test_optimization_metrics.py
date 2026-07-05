"""Tests for optimization metrics on findings."""

from app.finding_evidence import enrich_evidence
from app.optimization_metrics import build_optimization_metrics, attach_optimization_metrics
from app.metrics_loader import _parse_usage_value, _monitor_payload


def test_build_vm_optimization_metrics():
    finding = {
        "resource_type": "compute/vm",
        "estimated_savings_usd": 72.0,
        "confidence_score": 85,
    }
    evidence = {
        "avg_cpu_pct": 2.5,
        "vm_size": "Standard_D4s_v3",
        "power_state": "running",
        "monthly_cost_usd": 120.0,
        "data_source": "synced_inventory",
    }
    metrics = build_optimization_metrics(evidence, finding=finding, rule_id="VM_IDLE", resource_type="compute/vm")

    cost_ids = {m["id"] for m in metrics["cost"]}
    perf_ids = {m["id"] for m in metrics["performance"]}

    assert "mtd_cost" in cost_ids
    assert "estimated_savings" in cost_ids
    assert "savings_opportunity_pct" not in cost_ids
    assert "avg_cpu" in perf_ids
    assert "vm_size" in perf_ids
    assert "confidence_score" not in perf_ids
    assert metrics["data_quality"] == "inventory_and_cost"
    assert metrics["component"] == "compute/vm"

    cpu = next(m for m in metrics["performance"] if m["id"] == "avg_cpu")
    assert cpu["status"] == "underutilized"
    assert cpu["formatted"] == "2.5%"


def test_enrich_evidence_includes_optimization_metrics():
    out = enrich_evidence(
        "VM_IDLE",
        {"avg_cpu_pct": 3.0, "monthly_cost_usd": 50.0, "vm_size": "Standard_B2s"},
        {"estimated_savings_usd": 45.0, "resource_type": "compute/vm"},
    )
    assert "optimization_metrics" in out
    assert out["optimization_metrics"]["cost"]
    assert out["optimization_metrics"]["performance"]


def test_app_gateway_metrics_rule_scoped():
    metrics = build_optimization_metrics(
        {"http_listener_count": 0, "monthly_cost_usd": 80.0, "determination": "idle_no_listeners"},
        finding={"estimated_savings_usd": 80.0, "resource_type": "network/appgateway"},
        rule_id="APP_GATEWAY_IDLE_EXTENDED",
        resource_type="network/appgateway",
    )
    perf = {m["id"]: m for m in metrics["performance"]}
    assert perf["http_listeners"]["value"] == 0
    assert "mtd_cost" in {m["id"] for m in metrics["cost"]}
    assert metrics["display_mode"] == "rule_scoped"
    assert all(m.get("status") != "unavailable" for m in metrics["performance"])


def test_parse_k8s_usage_strings():
    assert _parse_usage_value("12.5%") == 12.5
    assert _parse_usage_value("250m") == 25.0
    assert _parse_usage_value("0.42") == 42.0


def test_monitor_payload_shape():
    payload = _monitor_payload(10.0, 55.0)
    assert len(payload["value"]) == 2
    assert payload["value"][0]["name"]["value"] == "cpuUsage"


def test_attach_optimization_metrics_preserves_evidence():
    base = {"monthly_cost_usd": 10.0, "disk_state": "Unattached"}
    out = attach_optimization_metrics(
        base,
        finding={"estimated_savings_usd": 10.0, "resource_type": "compute/disk"},
        rule_id="DISK_UNATTACHED",
    )
    assert out["disk_state"] == "Unattached"
    assert "optimization_metrics" in out


def test_disk_metrics_dedupe_state_and_context_fields():
    metrics = build_optimization_metrics(
        {
            "disk_state": "Unattached",
            "state": "Unattached",
            "sku": "Premium_LRS",
            "size_gb": 128,
            "resource_group": "MC_RG",
            "arm_resource_type": "microsoft.compute/disks",
            "monthly_cost_usd": 40.0,
        },
        finding={"estimated_savings_usd": 40.0, "resource_type": "compute/disk"},
        rule_id="DISK_UNATTACHED",
        resource_type="compute/disk",
    )
    perf = {m["id"]: m for m in metrics["performance"]}
    assert "disk_state" in perf
    assert "resource_state" not in perf
    assert "resource_group" not in perf
    assert "arm_resource_type" not in perf
    assert perf["disk_state"]["formatted"] == "Unattached"


def test_disk_optimization_metrics_datetime_includes_time():
    from datetime import datetime, timezone

    ts = datetime(2026, 4, 23, 12, 11, 15, tzinfo=timezone.utc)
    metrics = build_optimization_metrics(
        {"last_ownership_update": ts.isoformat(), "disk_state": "Unattached"},
        resource_type="compute/disk",
    )
    perf = {m["id"]: m for m in metrics["performance"]}
    assert "12:11 PM" in perf["last_ownership_update"]["formatted"]
    assert "Apr 23, 2026" in perf["last_ownership_update"]["formatted"]


def test_disk_optimization_metrics_from_lineage_timestamps():
    from datetime import datetime, timedelta, timezone

    detached = datetime.now(timezone.utc) - timedelta(days=30)
    created = datetime.now(timezone.utc) - timedelta(days=90)
    metrics = build_optimization_metrics(
        {
            "disk_state": "Unattached",
            "size_gb": 128,
            "sku": "Premium_LRS",
            "properties": {
                "timeCreated": created.isoformat(),
                "lastOwnershipUpdateTime": detached.isoformat(),
                "lastManagedBy": (
                    "/subscriptions/s/resourceGroups/rg/providers/"
                    "Microsoft.Compute/virtualMachines/old-vm"
                ),
            },
            "monthly_cost_usd": 45.0,
            "data_source": "synced_inventory",
        },
        finding={"estimated_savings_usd": 45.0, "resource_type": "compute/disk"},
        rule_id="DISK_UNUSED_EXTENDED",
        resource_type="compute/disk",
    )
    perf = {m["id"]: m for m in metrics["performance"]}
    assert perf["age_days"]["formatted"] != "Not available"
    assert perf["age_days"]["value"] >= 30
    assert perf["last_owner"]["formatted"] == "old-vm"
    assert perf["time_created"]["formatted"] != "Not available"
    assert perf["last_ownership_update"]["formatted"] != "Not available"
