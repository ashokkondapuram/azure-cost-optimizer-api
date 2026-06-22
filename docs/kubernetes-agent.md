# Kubernetes Agent

## Purpose
The Kubernetes utilization agent provides lightweight visibility into node and pod resource consumption without deploying a full monitoring platform.

## Runtime behavior
- Runs as a single pod.
- Polls `metrics.k8s.io` every configured interval.
- Collects node CPU and memory usage.
- Collects pod/container CPU and memory usage.
- Pushes snapshots to the backend API.

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
- `metrics.k8s.io` nodes
- `metrics.k8s.io` pods

## Resource footprint
The deployment is intentionally lightweight and configured with low CPU and memory requests/limits. This makes it suitable for simple telemetry ingestion where Prometheus-level depth is not required.

## Enterprise recommendations
For enterprise production use:
- package it as a proper container image rather than runtime `pip install`,
- pin dependencies and scan the image,
- sign the image,
- use outbound authentication to the backend,
- implement retry/backoff and dead-letter handling,
- add telemetry and health endpoints,
- support multiple clusters via cluster registration.
