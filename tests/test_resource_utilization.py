"""Tests for monitor-backed resource utilization helpers."""

from app.resource_utilization import (
    confidence_with_monitor,
    cpu_pct,
    has_monitor_data,
    has_required_facts,
    is_idle_io,
    is_idle_keyvault,
    is_idle_public_ip_traffic,
    is_low_cpu,
    is_low_cpu_time,
    is_low_request_volume,
    is_low_traffic,
    make_check,
    metrics_block_rightsize,
    monitor_evidence,
    monitor_facts_status,
    structured_evidence,
    utilization_gate,
    utilization_savings_factor,
    webapp_utilization_summary,
)


def test_has_monitor_data_from_technical_facts():
    resource = {"_technical_facts": {"avg_cpu_pct": 12.5, "data_source": "azure_monitor"}}
    assert has_monitor_data(resource) is True
    assert cpu_pct(resource) == 12.5


def test_is_low_cpu_and_block_rightsize():
    low = {"_technical_facts": {"cpu_pct": 8.0}}
    high = {"_technical_facts": {"cpu_pct": 82.0}}
    assert is_low_cpu(low) is True
    assert metrics_block_rightsize(high) is True


def test_is_idle_io_for_disks():
    disk = {"_technical_facts": {"disk_read_bps": 10.0, "disk_write_bps": 5.0}}
    assert is_idle_io(disk) is True


def test_is_low_traffic_for_network():
    lb = {"_technical_facts": {"byte_count": 100.0}}
    assert is_low_traffic(lb) is True


def test_confidence_with_monitor_boost():
    resource = {"_technical_facts": {"transaction_count": 12.0}}
    assert confidence_with_monitor(60, resource) == 72


def test_monitor_evidence_merges_extra():
    resource = {"_technical_facts": {"cpu_pct": 4.0}}
    evidence = monitor_evidence(resource, {"monthly_cost_usd": 25.0})
    assert evidence["cpu_pct"] == 4.0
    assert evidence["data_source"] == "azure_monitor"
    assert evidence["monthly_cost_usd"] == 25.0


def test_webapp_utilization_helpers():
    idle = {"_technical_facts": {"cpu_time_sec": 120.0, "request_count": 42.0}}
    busy = {"_technical_facts": {"cpu_time_sec": 7200.0, "request_count": 5000.0}}
    assert is_low_cpu_time(idle) is True
    assert is_low_cpu_time(busy) is False
    assert is_low_request_volume(idle, threshold=500.0) is True
    summary = webapp_utilization_summary(idle)
    assert "CPU time 120s" in summary
    assert "42 requests" in summary


def test_monitor_facts_status_and_utilization_gate():
    no_monitor = {"_technical_facts": {"vm_size": "Standard_D2s_v3"}}
    partial = {"_technical_facts": {"data_source": "azure_monitor", "byte_count": 10.0}}
    complete = {"_technical_facts": {"data_source": "azure_monitor", "byte_count": 10.0, "packet_count": 2.0}}

    assert monitor_facts_status(no_monitor, "byte_count") == "no_monitor"
    assert monitor_facts_status(partial, "byte_count", "packet_count") == "partial"
    assert monitor_facts_status(complete, "byte_count", "packet_count") == "available"
    assert utilization_gate(complete, "byte_count", "packet_count", allow_inventory_only=False) is True
    assert utilization_gate(partial, "byte_count", "packet_count", allow_inventory_only=False) is False
    assert utilization_gate(no_monitor, "byte_count", allow_inventory_only=True) is True


def test_structured_evidence_and_idle_helpers():
    ip = {"_technical_facts": {"data_source": "azure_monitor", "byte_count": 50.0, "packet_count": 5.0}}
    assert is_idle_public_ip_traffic(ip) is True
    assert has_required_facts(ip, "byte_count", "packet_count") is True

    vault = {"_technical_facts": {"data_source": "azure_monitor", "api_hits": 2.0}}
    assert is_idle_keyvault(vault) is True

    evidence = structured_evidence(
        ip,
        determination="associated_low_traffic",
        summary="Low traffic public IP",
        checks=[make_check("Byte count", 50.0, "< 1,000", passed=True)],
    )
    assert evidence["determination"] == "associated_low_traffic"
    assert evidence["metrics_available"] is True
    assert evidence["checks"][0]["passed"] is True


def test_utilization_savings_factor():
    assert utilization_savings_factor(100.0, 10.0) == 50.0
    assert utilization_savings_factor(100.0, 25.0) == 35.0
    assert utilization_savings_factor(100.0, 55.0) == 0.0

