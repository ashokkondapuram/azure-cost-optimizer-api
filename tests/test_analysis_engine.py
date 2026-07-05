"""Smoke tests for optimization analysis engines."""

from app.analysis import empty_buckets, run_engine_on_buckets
from app.optimizer.extended_engine import ExtendedOptimizationEngine
from app.optimizer.engine import OptimizationEngine


def _sample_vm(rid_suffix: str = "vm1") -> dict:
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


def test_extended_engine_imports_and_analyzes():
    eng = ExtendedOptimizationEngine()
    assert len(eng.rules) > 0
    result = eng.analyze(
        subscription_id="abc",
        vms=[_sample_vm()],
        cost_by_resource={_sample_vm()["id"].lower(): 150.0},
    )
    assert "summary" in result
    assert result["engine_version"] == "extended"
    assert isinstance(result["findings"], list)


def test_standard_engine_analyzes_vm_with_cost():
    eng = OptimizationEngine()
    vm = _sample_vm("vm2")
    result = eng.analyze(
        vms=[vm],
        cost_by_resource={vm["id"].lower(): 200.0},
    )
    assert result["summary"]["total_findings"] >= 0
    for finding in result["findings"]:
        assert finding["rule_id"]
        assert "evidence" in finding
        assert "optimization_metrics" in finding["evidence"]


def test_run_engine_on_buckets_extended_without_db_metrics():
    from app.database import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        buckets = empty_buckets()
        vm = _sample_vm("vm3")
        buckets["vms"] = [vm]
        cost = {vm["id"].lower(): 99.0}
        result = run_engine_on_buckets(
            db,
            subscription_id="abc",
            buckets=buckets,
            aks_node_pools={},
            cost_by_resource=cost,
            budgets=[],
            profile="default",
            engine_version="extended",
            vm_metrics={},
            node_metrics={},
            load_metrics=False,
        )
        assert result["engine_version"] == "extended"
        assert "metrics_context" in result
    finally:
        db.close()
