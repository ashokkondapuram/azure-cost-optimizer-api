# In-cluster utilization agent

A single lightweight pod that reads **metrics-server** data and cluster inventory, then pushes batched snapshots to the FinOps API.

## What it collects

| Data | Source |
|------|--------|
| Node capacity, allocatable, CPU/memory usage | `metrics.k8s.io` + Core API |
| Pod phase, restarts, requests/limits vs usage | Core API + `metrics.k8s.io` |
| Cluster summary (utilization %, counts by phase) | Aggregated in-agent |

**Footprint:** ~25m CPU / 64Mi RAM request, 100m / 128Mi limit.

## Prerequisites

1. **metrics-server** running in the cluster (`kubectl get apiservice v1beta1.metrics.k8s.io`)
2. Network path from the cluster to your FinOps API
3. Optional: set `K8S_AGENT_TOKEN` on the API and matching `API_TOKEN` in the Secret

## Build the image

```bash
cd k8s
docker build -t finops/k8s-agent:1.0 .
```

For AKS, push to your registry:

```bash
ACR=myregistry.azurecr.io
az acr login --name ${ACR%%.azurecr.io}
docker tag finops/k8s-agent:1.0 $ACR/finops/k8s-agent:1.0
docker push $ACR/finops/k8s-agent:1.0
```

Update `image:` in `utilization-agent.yaml` to your registry path.

## Deploy

1. Edit `utilization-agent.yaml`:
   - `API_URL` — your API base URL (e.g. `https://finops-api.example.com`)
   - `CLUSTER_NAME` — logical name for this cluster
   - `POLL_INTERVAL` — seconds between snapshots (default `60`)

2. Apply:

```bash
kubectl apply -f utilization-agent.yaml
```

3. Verify:

```bash
kubectl -n finops-agent logs -l app=utilization-agent -f
kubectl -n finops-agent get pods
```

4. Query the API:

```bash
curl "http://127.0.0.1:8000/k8s/snapshot?cluster_name=my-aks-cluster"
```

## Local test (outside cluster)

```bash
export API_URL=http://127.0.0.1:8000
export CLUSTER_NAME=local-dev
pip install -r requirements.txt
python agent.py
```

Uses your current kubeconfig context.

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/k8s/snapshot` | Batched cluster snapshot (used by agent) |
| `GET` | `/k8s/snapshot` | Latest snapshot per cluster |
| `POST` | `/k8s/utilization` | Legacy single-row metric push |

## Security

- RBAC is read-only (`get`, `list` on nodes, pods, namespaces, metrics)
- Runs as non-root UID 10001
- Optional `X-API-Key` header when `K8S_AGENT_TOKEN` is configured on the API
