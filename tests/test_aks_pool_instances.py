"""Tests for AKS VMSS pool instance listing and metrics enrichment."""

from it_services.containers_aks.pool_instances import (
    _basic_instance_row,
    _match_k8s_instance,
    _metrics_from_detail,
    attach_vmss_instances_to_pools,
    enrich_pool_vmss_instances,
    list_vmss_instances_basic,
    vmss_instance_power_state,
)


def _vmss_vm(name: str = "aks-system-123-vmss000000", instance_id: str = "0") -> dict:
    return {
        "id": (
            "/subscriptions/sub-a/resourceGroups/MC_rg/providers/"
            f"Microsoft.Compute/virtualMachineScaleSets/aks-system-123-vmss/virtualMachines/{instance_id}"
        ),
        "name": name,
        "properties": {
            "instanceId": instance_id,
            "osProfile": {"computerName": name},
            "instanceView": {
                "statuses": [{"code": "PowerState/running"}],
            },
        },
    }


def test_basic_instance_row_extracts_fields():
    row = _basic_instance_row(_vmss_vm())
    assert row["name"] == "aks-system-123-vmss000000"
    assert row["instance_id"] == "0"
    assert row["power_state"] == "running"
    assert row["computer_name"] == "aks-system-123-vmss000000"


def test_vmss_instance_power_state_from_instance_view():
    assert vmss_instance_power_state(_vmss_vm()) == "running"


def test_metrics_from_detail_supports_node_and_vm_keys():
    cpu, mem = _metrics_from_detail([
        {"fact_key": "node_cpu_pct", "stats": {"average": 22.5}},
        {"fact_key": "avg_memory_pct", "stats": {"average": 61.0}},
    ])
    assert cpu == 22.5
    assert mem == 61.0


def test_match_k8s_instance_by_computer_name():
    k8s = [{
        "name": "aks-system-123-vmss000000",
        "pool_name": "system",
        "metrics_detail": [
            {"fact_key": "node_cpu_pct", "stats": {"average": 30}},
            {"fact_key": "node_mem_pct", "stats": {"average": 50}},
        ],
    }]
    matched = _match_k8s_instance(
        k8s,
        pool_name="system",
        computer_name="aks-system-123-vmss000000",
        instance_name="aks-system-123-vmss000000",
    )
    assert matched is not None
    cpu, mem = _metrics_from_detail(matched["metrics_detail"])
    assert cpu == 30.0
    assert mem == 50.0


class _FakeClient:
    def __init__(self, instances=None):
        self.instances = instances or [_vmss_vm(), _vmss_vm("aks-system-123-vmss000001", "1")]
        self.metric_calls = 0

    def list_vm_scale_set_vms(self, subscription_id, resource_group, vmss_name):
        return self.instances

    def get_resource_metrics(self, resource_id, **kwargs):
        self.metric_calls += 1
        return {
            "value": [
                {
                    "name": {"value": "Percentage CPU"},
                    "timeseries": [{"data": [{"average": 18.0}]}],
                },
                {
                    "name": {"value": "Available Memory Bytes"},
                    "timeseries": [{"data": [{"average": 2_000_000_000}]}],
                },
            ],
        }


def test_list_vmss_instances_basic():
    client = _FakeClient()
    vmss_id = (
        "/subscriptions/sub-a/resourceGroups/MC_rg/providers/"
        "Microsoft.Compute/virtualMachineScaleSets/aks-system-123-vmss"
    )
    rows = list_vmss_instances_basic(client, "sub-a", vmss_id)
    assert len(rows) == 2
    assert rows[0]["instance_id"] == "0"


def test_attach_vmss_instances_to_pools_during_sync():
    pools = [{
        "name": "system",
        "count": 2,
        "virtualMachineScaleSet": {
            "id": (
                "/subscriptions/sub-a/resourceGroups/MC_rg/providers/"
                "Microsoft.Compute/virtualMachineScaleSets/aks-system-123-vmss"
            ),
        },
    }]
    enriched = attach_vmss_instances_to_pools(_FakeClient(), "sub-a", pools)
    assert len(enriched[0]["vmssInstances"]) == 2
    assert enriched[0]["vmssInstances"][0]["instance_id"] == "0"


def test_attach_vmss_instances_to_pools_uses_vmss_by_pool():
    pools = [{"name": "user", "count": 3, "vmSize": "Standard_D4s_v3"}]
    vmss_by_pool = {
        "user": {
            "id": (
                "/subscriptions/sub-a/resourceGroups/MC_rg/providers/"
                "Microsoft.Compute/virtualMachineScaleSets/aks-user-123-vmss"
            ),
        },
    }
    client = _FakeClient(instances=[_vmss_vm("aks-user-123-vmss000000", "0")])
    enriched = attach_vmss_instances_to_pools(
        client,
        "sub-a",
        pools,
        vmss_by_pool=vmss_by_pool,
    )
    assert len(enriched[0]["vmssInstances"]) == 1
    assert enriched[0]["vmssInstances"][0]["instance_id"] == "0"


def test_enrich_pool_vmss_instances_prefers_k8s_metrics():
    client = _FakeClient(instances=[_vmss_vm()])
    vmss_id = (
        "/subscriptions/sub-a/resourceGroups/MC_rg/providers/"
        "Microsoft.Compute/virtualMachineScaleSets/aks-system-123-vmss"
    )
    rows = enrich_pool_vmss_instances(
        client,
        "sub-a",
        "system",
        vmss_id,
        vm_size="Standard_D2s_v3",
        k8s_instances=[{
            "name": "aks-system-123-vmss000000",
            "pool_name": "system",
            "metrics_detail": [
                {"fact_key": "node_cpu_pct", "stats": {"average": 44}},
                {"fact_key": "node_mem_pct", "stats": {"average": 66}},
            ],
        }],
        timespan="P7D",
        db=None,
    )
    assert rows[0]["cpu_pct"] == 44.0
    assert rows[0]["mem_pct"] == 66.0
    assert rows[0]["source"] == "k8s_agent"
    assert client.metric_calls == 0


def test_enrich_pool_vmss_instances_falls_back_to_azure_monitor():
    client = _FakeClient(instances=[_vmss_vm()])
    vmss_id = (
        "/subscriptions/sub-a/resourceGroups/MC_rg/providers/"
        "Microsoft.Compute/virtualMachineScaleSets/aks-system-123-vmss"
    )
    rows = enrich_pool_vmss_instances(
        client,
        "sub-a",
        "system",
        vmss_id,
        vm_size="Standard_D2s_v3",
        k8s_instances=[],
        timespan="P7D",
        db=None,
    )
    assert rows[0]["cpu_pct"] == 18.0
    assert rows[0]["source"] == "azure_monitor"
    assert client.metric_calls == 1


def test_enrich_pool_vmss_instances_prefers_live_inventory_over_cache():
    live_instances = [_vmss_vm(), _vmss_vm("aks-system-123-vmss000001", "1")]
    client = _FakeClient(instances=live_instances)
    vmss_id = (
        "/subscriptions/sub-a/resourceGroups/MC_rg/providers/"
        "Microsoft.Compute/virtualMachineScaleSets/aks-system-123-vmss"
    )
    cached = [{"id": live_instances[0]["id"], "name": live_instances[0]["name"], "instance_id": "0"}]
    rows = enrich_pool_vmss_instances(
        client,
        "sub-a",
        "system",
        vmss_id,
        cached_instances=cached,
        timespan="P7D",
        db=None,
    )
    assert len(rows) == 2


def test_instance_metrics_distinct_from_cluster_aggregate():
    """Per-instance CPU must not inherit cluster_cpu_pct."""
    class _PerInstanceClient(_FakeClient):
        def get_resource_metrics(self, resource_id, **kwargs):
            self.metric_calls += 1
            inst_id = str(resource_id).rsplit("/", 1)[-1]
            cpu = 12.0 if inst_id == "0" else 34.0
            return {
                "value": [{
                    "name": {"value": "Percentage CPU"},
                    "timeseries": [{"data": [{"average": cpu}]}],
                }],
            }

    client = _PerInstanceClient(instances=[
        _vmss_vm(),
        _vmss_vm("aks-system-123-vmss000001", "1"),
    ])
    vmss_id = (
        "/subscriptions/sub-a/resourceGroups/MC_rg/providers/"
        "Microsoft.Compute/virtualMachineScaleSets/aks-system-123-vmss"
    )
    rows = enrich_pool_vmss_instances(
        client,
        "sub-a",
        "system",
        vmss_id,
        vm_size="Standard_D2s_v3",
        k8s_instances=[],
        timespan="P7D",
        db=None,
    )
    cluster_cpu = 55.0
    assert rows[0]["cpu_pct"] != cluster_cpu
    assert rows[1]["cpu_pct"] != cluster_cpu
    assert rows[0]["cpu_pct"] != rows[1]["cpu_pct"]
