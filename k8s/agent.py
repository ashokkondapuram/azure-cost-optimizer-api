"""
Lightweight in-cluster agent — polls metrics-server and pushes a batched snapshot
to the Cost Optimizer API. Designed for a single small pod (~64–128 Mi RAM).
"""
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from kubernetes import client, config
from kubernetes.client.rest import ApiException

API_URL = os.environ.get("API_URL", "").rstrip("/")
CLUSTER_NAME = os.environ.get("CLUSTER_NAME", "unknown")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))
API_TOKEN = os.environ.get("API_TOKEN", "")
HEARTBEAT_FILE = os.environ.get("HEARTBEAT_FILE", "/tmp/agent-heartbeat")
BATCH_ENDPOINT = os.environ.get("BATCH_ENDPOINT", "/k8s/snapshot")

_CPU_RE = re.compile(r"^(\d+(?:\.\d+)?)(m)?$")
_MEM_RE = re.compile(r"^(\d+(?:\.\d+)?)(Ki|Mi|Gi|Ti|K|M|G|T)?$")


def load_k8s_config():
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def _cpu_to_millicores(value: str | None) -> int:
    if not value:
        return 0
    m = _CPU_RE.match(str(value).strip())
    if not m:
        return 0
    num = float(m.group(1))
    return int(num if m.group(2) else num * 1000)


def _mem_to_bytes(value: str | None) -> int:
    if not value:
        return 0
    m = _MEM_RE.match(str(value).strip())
    if not m:
        return 0
    num = float(m.group(1))
    suffix = m.group(2) or ""
    mult = {
        "": 1, "K": 1000, "M": 1000 ** 2, "G": 1000 ** 3, "T": 1000 ** 4,
        "Ki": 1024, "Mi": 1024 ** 2, "Gi": 1024 ** 3, "Ti": 1024 ** 4,
    }.get(suffix, 1)
    return int(num * mult)


def _node_instance_type(labels: dict) -> str | None:
    return (
        labels.get("node.kubernetes.io/instance-type")
        or labels.get("beta.kubernetes.io/instance-type")
    )


def _requests_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if API_TOKEN:
        headers["X-API-Key"] = API_TOKEN
    return headers


def _list_metrics(metrics_api: client.CustomObjectsApi, plural: str) -> list:
    try:
        data = metrics_api.list_cluster_custom_object(
            group="metrics.k8s.io", version="v1beta1", plural=plural
        )
        return data.get("items", [])
    except ApiException as exc:
        print(f"metrics.k8s.io/{plural} unavailable: {exc.reason}", file=sys.stderr)
        return []


def collect_snapshot(core: client.CoreV1Api, metrics_api: client.CustomObjectsApi) -> dict:
    nodes = core.list_node().items
    pods = core.list_pod_for_all_namespaces().items
    namespaces = core.list_namespace().items

    node_metrics = {
        item["metadata"]["name"]: item.get("usage", {})
        for item in _list_metrics(metrics_api, "nodes")
    }
    pod_metrics = {
        (item["metadata"]["namespace"], item["metadata"]["name"]): item
        for item in _list_metrics(metrics_api, "pods")
    }

    node_rows = []
    total_cpu_cap = total_mem_cap = total_cpu_use = total_mem_use = 0
    ready_nodes = 0

    for node in nodes:
        name = node.metadata.name
        labels = node.metadata.labels or {}
        usage = node_metrics.get(name, {})
        cap = node.status.capacity or {}
        alloc = node.status.allocatable or {}
        cpu_cap = _cpu_to_millicores(cap.get("cpu"))
        mem_cap = _mem_to_bytes(cap.get("memory"))
        cpu_use = _cpu_to_millicores(usage.get("cpu"))
        mem_use = _mem_to_bytes(usage.get("memory"))
        total_cpu_cap += cpu_cap
        total_mem_cap += mem_cap
        total_cpu_use += cpu_use
        total_mem_use += mem_use

        conditions = {c.type: c.status for c in (node.status.conditions or [])}
        if conditions.get("Ready") == "True":
            ready_nodes += 1

        node_rows.append({
            "name": name,
            "instance_type": _node_instance_type(labels),
            "zone": labels.get("topology.kubernetes.io/zone") or labels.get("failure-domain.beta.kubernetes.io/zone"),
            "pool": labels.get("agentpool") or labels.get("kubernetes.azure.com/agentpool"),
            "ready": conditions.get("Ready") == "True",
            "schedulable": not node.spec.unschedulable,
            "capacity": {"cpu": cap.get("cpu"), "memory": cap.get("memory"), "pods": cap.get("pods")},
            "allocatable": {"cpu": alloc.get("cpu"), "memory": alloc.get("memory"), "pods": alloc.get("pods")},
            "usage": {"cpu": usage.get("cpu"), "memory": usage.get("memory")},
            "cpu_utilization_pct": round(cpu_use / cpu_cap * 100, 1) if cpu_cap else None,
            "memory_utilization_pct": round(mem_use / mem_cap * 100, 1) if mem_cap else None,
        })

    pod_rows = []
    phases = {"Running": 0, "Pending": 0, "Failed": 0, "Succeeded": 0, "Unknown": 0}

    for pod in pods:
        phase = pod.status.phase or "Unknown"
        phases[phase] = phases.get(phase, 0) + 1
        key = (pod.metadata.namespace, pod.metadata.name)
        metrics = pod_metrics.get(key, {})
        metric_containers = {
            c["name"]: c.get("usage", {})
            for c in metrics.get("containers", [])
        }

        containers = []
        for c in (pod.spec.containers or []):
            req = (c.resources.requests or {}) if c.resources else {}
            lim = (c.resources.limits or {}) if c.resources else {}
            use = metric_containers.get(c.name, {})
            containers.append({
                "name": c.name,
                "requests": {"cpu": req.get("cpu"), "memory": req.get("memory")},
                "limits": {"cpu": lim.get("cpu"), "memory": lim.get("memory")},
                "usage": {"cpu": use.get("cpu"), "memory": use.get("memory")},
            })

        owner = None
        if pod.metadata.owner_references:
            ref = pod.metadata.owner_references[0]
            owner = {"kind": ref.kind, "name": ref.name}

        pod_rows.append({
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "node": pod.spec.node_name,
            "phase": phase,
            "restart_count": sum(
                (cs.restart_count or 0) for cs in (pod.status.container_statuses or [])
            ),
            "owner": owner,
            "containers": containers,
        })

    return {
        "cluster_name": CLUSTER_NAME,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "node_count": len(nodes),
            "ready_nodes": ready_nodes,
            "pod_count": len(pods),
            "namespace_count": len(namespaces),
            "pods_by_phase": phases,
            "total_cpu_capacity_m": total_cpu_cap,
            "total_memory_capacity_bytes": total_mem_cap,
            "total_cpu_usage_m": total_cpu_use,
            "total_memory_usage_bytes": total_mem_use,
            "cluster_cpu_utilization_pct": round(total_cpu_use / total_cpu_cap * 100, 1) if total_cpu_cap else None,
            "cluster_memory_utilization_pct": round(total_mem_use / total_mem_cap * 100, 1) if total_mem_cap else None,
        },
        "nodes": node_rows,
        "pods": pod_rows,
    }


def push_snapshot(snapshot: dict) -> None:
    if not API_URL:
        raise RuntimeError("API_URL is required")

    url = f"{API_URL}{BATCH_ENDPOINT}"
    resp = requests.post(url, json=snapshot, headers=_requests_headers(), timeout=30)
    resp.raise_for_status()
    with open(HEARTBEAT_FILE, "w", encoding="utf-8") as fh:
        fh.write(snapshot["collected_at"])


def collect_and_push():
    core = client.CoreV1Api()
    metrics_api = client.CustomObjectsApi()
    snapshot = collect_snapshot(core, metrics_api)
    push_snapshot(snapshot)
    summary = snapshot["summary"]
    print(
        f"Pushed snapshot: {summary['node_count']} nodes, {summary['pod_count']} pods, "
        f"CPU {summary.get('cluster_cpu_utilization_pct')}% / "
        f"mem {summary.get('cluster_memory_utilization_pct')}%"
    )


def main():
    load_k8s_config()
    print(f"FinOps agent started — cluster={CLUSTER_NAME}, interval={POLL_INTERVAL}s, api={API_URL}")
    while True:
        try:
            collect_and_push()
        except Exception as exc:
            print(f"Collection cycle failed: {exc}", file=sys.stderr)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
