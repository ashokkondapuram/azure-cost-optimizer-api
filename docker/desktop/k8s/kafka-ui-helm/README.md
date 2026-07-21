# Kafka UI — Helm (Kubernetes)

Web UI for browsing Kafka topics, messages, and consumer groups when running the stack on **Docker Desktop Kubernetes** (or any local cluster).

## Why Kafbat, not Provectus charts?

| Source | Chart repo | Default image | Status |
|--------|------------|---------------|--------|
| [provectus/kafka-ui-charts](https://provectus.github.io/kafka-ui-charts) | `kafka-ui/kafka-ui` | `docker.io/provectuslabs/kafka-ui` | **Blocked** for Zafin org on Docker Hub |
| [kafbat/helm-charts](https://ui.charts.kafbat.io) | `kafbat/kafka-ui` | `ghcr.io/kafbat/kafka-ui` | **Use this** — same UI, GHCR image |

Kafbat UI is the maintained successor to Provectus kafka-ui. The Helm chart API (`yamlApplicationConfig`, env maps) matches the Provectus chart closely.

## Prerequisites

- `helm` 3.x
- A running Kubernetes cluster (Docker Desktop → Enable Kubernetes)
- Kafka broker reachable from the cluster at `redpanda:9092` (default in `values.yaml`)

### Kafka bootstrap address

`values.yaml` assumes a broker Service named `redpanda` on port `9092` in the `costoptimize` namespace.

| Broker runs in… | Set `bootstrapServers` to |
|----------------|---------------------------|
| K8s Service `redpanda` in `costoptimize` | `redpanda:9092` (default) |
| Docker Compose on the host (`127.0.0.1:9092`) | `host.docker.internal:9092` |

Override at install time:

```bash
helm upgrade --install costoptimize-kafka-ui kafbat/kafka-ui \
  -n costoptimize --create-namespace \
  -f docker/desktop/k8s/kafka-ui-helm/values.yaml \
  --set yamlApplicationConfig.kafka.clusters[0].bootstrapServers=host.docker.internal:9092
```

## Install

From the repository root:

```bash
helm repo add kafbat https://ui.charts.kafbat.io
helm repo update

helm upgrade --install costoptimize-kafka-ui kafbat/kafka-ui \
  -n costoptimize --create-namespace \
  -f docker/desktop/k8s/kafka-ui-helm/values.yaml
```

Open the UI: [http://127.0.0.1:30085](http://127.0.0.1:30085) (NodePort `30085`).

## Uninstall

```bash
helm uninstall costoptimize-kafka-ui -n costoptimize
```

## Compose alternative

For Docker Compose dev, use **Redpanda Console** on [http://127.0.0.1:8085](http://127.0.0.1:8085) — see [services/README.md](../../../../services/README.md).

## Parent

[docker/desktop/k8s/](../) · [services/README.md](../../../../services/README.md)
