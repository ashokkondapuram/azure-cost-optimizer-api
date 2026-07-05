"""Tests for per-resource optimization sub-engines."""

from app.optimizer.extended_engine import ExtendedOptimizationEngine
from app.optimizer.resource_engines.runtime.envelope import build_resource_envelope, resolve_canonical_type
from app.optimizer.resource_engines.runtime.context import AnalysisContext
from app.optimizer.resource_engines.registry import list_sub_engines, run_sub_engines


def _vm(rid_suffix: str = "vm1") -> dict:
    return {
        "id": f"/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/{rid_suffix}",
        "name": rid_suffix,
        "type": "Microsoft.Compute/virtualMachines",
        "location": "eastus",
        "properties": {
            "hardwareProfile": {"vmSize": "Standard_D4s_v3"},
            "instanceView": {"statuses": [{"code": "PowerState/running"}]},
        },
        "tags": {"Environment": "dev"},
    }


def test_resolve_canonical_type_from_arm_id():
    vm = _vm()
    assert resolve_canonical_type(vm) == "compute/vm"


def test_resource_envelope_includes_configuration_and_cost():
    vm = _vm()
    ctx = AnalysisContext(
        subscription_id="abc",
        rules={},
        cost_by_resource={vm["id"].lower(): 120.0},
    )
    envelope = build_resource_envelope(vm, ctx)
    assert envelope.canonical_type == "compute/vm"
    assert envelope.monthly_cost == 120.0
    assert envelope.elements["configuration"].get("vm_size") or envelope.facts.get("vm_size")
    assert envelope.elements["cost"]["monthly_usd"] == 120.0


def test_sub_engines_registered_per_analysis_batch():
    engines = list_sub_engines()
    components = {e["component"] for e in engines}
    assert "Virtual Machines" in components
    assert "Virtual Machine Scale Sets" in components
    assert "Application Gateways" in components
    assert len(engines) >= 17


def test_run_sub_engines_attaches_resource_elements_to_evidence():
    eng = ExtendedOptimizationEngine()
    vm = _vm()
    ctx = AnalysisContext(
        subscription_id="abc",
        rules=eng.rules,
        cost_by_resource={vm["id"].lower(): 200.0},
    )
    findings = run_sub_engines(eng, ctx, {"vms": [vm]})
    assert isinstance(findings, list)
    if findings:
        assert "resource_elements" in findings[0].evidence
        assert findings[0].evidence["resource_elements"]["canonical_type"] == "compute/vm"


def test_extended_engine_uses_sub_engines():
    eng = ExtendedOptimizationEngine()
    vm = _vm("vm-sub")
    result = eng.analyze(
        subscription_id="abc",
        vms=[vm],
        cost_by_resource={vm["id"].lower(): 150.0},
    )
    assert result["engine_version"] == "extended"
    for finding in result["findings"]:
        ev = finding.get("evidence") or {}
        if finding.get("resource_id", "").lower() == vm["id"].lower():
            assert "resource_elements" in ev
            break


def test_public_ip_low_traffic_requires_monitor_facts():
    from app.optimizer.resource_engines.network.publicip.analysis import analyze_public_ips

    eng = ExtendedOptimizationEngine()
    rid = "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/pip-idle"
    ip = {
        "id": rid,
        "name": "pip-idle",
        "properties": {
            "publicIPAllocationMethod": "Static",
            "ipConfiguration": {"id": "/subscriptions/abc/.../nic/ipconfig"},
        },
    }
    ip["_technical_facts"] = {
        "data_source": "azure_monitor",
        "byte_count": 10.0,
        "packet_count": 2.0,
    }
    findings = analyze_public_ips(eng, "abc", [ip], {rid.lower(): 5.0})
    assert len(findings) == 1
    assert findings[0].evidence["determination"] == "associated_low_traffic"


def test_sql_serverless_skips_without_cpu_metrics():
    from app.optimizer.resource_engines.database.sql.analysis import analyze_sql

    eng = ExtendedOptimizationEngine()
    db = {
        "id": "/subscriptions/abc/resourceGroups/rg/providers/Microsoft.Sql/servers/srv/databases/db1",
        "name": "db1",
        "sku": {"tier": "GeneralPurpose", "name": "GP_Gen5_2"},
        "_technical_facts": {"data_source": "azure_monitor"},
    }
    assert analyze_sql(eng, "abc", [db]) == []

    db["_technical_facts"]["cpu_pct"] = 8.0
    findings = analyze_sql(eng, "abc", [db])
    assert len(findings) == 1
    assert findings[0].evidence["determination"] == "serverless_candidate"

