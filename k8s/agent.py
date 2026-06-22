import os
import time
import requests
from kubernetes import client, config

API_URL = os.environ["API_URL"]
CLUSTER_NAME = os.environ.get("CLUSTER_NAME", "unknown")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))


def load_k8s_config():
    try:
        config.load_incluster_config()   # running inside a pod
    except Exception:
        config.load_kube_config()        # local fallback


def collect_and_push():
    core = client.CoreV1Api()
    metrics_api = client.CustomObjectsApi()

    # Node utilization from metrics-server
    try:
        node_metrics = metrics_api.list_cluster_custom_object(
            group="metrics.k8s.io", version="v1beta1", plural="nodes"
        )
        for item in node_metrics.get("items", []):
            payload = {
                "cluster_name": CLUSTER_NAME,
                "node_name": item["metadata"]["name"],
                "cpu_usage": item["usage"].get("cpu"),
                "memory_usage": item["usage"].get("memory")
            }
            requests.post(API_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"Node metrics error: {e}")

    # Pod utilization from metrics-server
    try:
        pod_metrics = metrics_api.list_cluster_custom_object(
            group="metrics.k8s.io", version="v1beta1", plural="pods"
        )
        for item in pod_metrics.get("items", []):
            for container in item.get("containers", []):
                payload = {
                    "cluster_name": CLUSTER_NAME,
                    "node_name": item["metadata"].get("name", ""),
                    "pod_name": item["metadata"]["name"],
                    "namespace": item["metadata"]["namespace"],
                    "cpu_usage": container["usage"].get("cpu"),
                    "memory_usage": container["usage"].get("memory")
                }
                requests.post(API_URL, json=payload, timeout=10)
    except Exception as e:
        print(f"Pod metrics error: {e}")


if __name__ == "__main__":
    load_k8s_config()
    print(f"Utilization agent started. Polling every {POLL_INTERVAL}s.")
    while True:
        collect_and_push()
        time.sleep(POLL_INTERVAL)
