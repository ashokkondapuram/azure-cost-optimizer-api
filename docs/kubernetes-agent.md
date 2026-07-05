# Kubernetes Agent

## Purpose
The Kubernetes utilization agent is a **single lightweight pod** (~64–128 Mi RAM) that provides cluster metrics and inventory without deploying Prometheus or a full monitoring stack.

## Runtime behavior
- Runs as one pod in the `finops-agent` namespace.
- Polls `metrics.k8s.io` every configured interval (default 60s).
- Collects node capacity, allocatable resources, and CPU/memory usage.
- Collects pod phase, restarts, requests/limits, and per-container usage.
- Pushes a **batched snapshot** to `POST /k8s/snapshot`.

## Quick deploy

```bash
cd k8s
docker build -t finops/k8s-agent:1.0 .
# Edit utilization-agent.yaml — set API_URL and CLUSTER_NAME
kubectl apply -f utilization-agent.yaml
```

See [k8s/README.md](../k8s/README.md) for full instructions.

## Dependencies
- Kubernetes cluster access.
- `metrics-server` installed and functioning.
- Network path from cluster to backend API.

## RBAC
The included manifest grants only read operations:
- `get`
- `list`

Resources covered:
- `nodes`
- `pods`
- `namespaces`
- `metrics.k8s.io` nodes
- `metrics.k8s.io` pods

## Resource footprint
| Resource | Request | Limit |
|----------|---------|-------|
| CPU | 25m | 100m |
| Memory | 64Mi | 128Mi |

## API endpoints
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/k8s/snapshot` | Batched cluster snapshot |
| `GET` | `/k8s/snapshot` | Latest snapshot for a cluster |
| `GET` | `/k8s/snapshots` | Recent snapshot history |
| `POST` | `/k8s/utilization` | Legacy per-row metric push |

## Security
- Optional `K8S_AGENT_TOKEN` on the API; agent sends `X-API-Key` header.
- Pod runs as non-root (UID 10001).
- Read-only cluster RBAC.

## Enterprise recommendations
For enterprise production use:
- push the image to a private registry (ACR) and pin by digest,
- scan and sign the image,
- use mutual TLS or API gateway auth for ingress,
- implement retry/backoff at the network edge if needed,
- register multiple clusters with distinct `CLUSTER_NAME` values.
