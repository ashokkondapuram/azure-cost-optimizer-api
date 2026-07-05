# Database

## Engine
The application uses PostgreSQL through SQLAlchemy.

## Current tables

### cost_records
Stores Azure cost query metadata and raw payloads.

Suggested columns currently represented in the ORM:
- `id`
- `subscription_id`
- `resource_group`
- `timeframe`
- `granularity`
- `pretax_cost`
- `currency`
- `billing_period`
- `raw_response`
- `created_at`

### k8s_utilization
Stores Kubernetes node and pod utilization snapshots.

Suggested columns currently represented in the ORM:
- `id`
- `cluster_name`
- `node_name`
- `pod_name`
- `namespace`
- `cpu_usage`
- `memory_usage`
- `recorded_at`

## Production schema recommendations
For enterprise-grade delivery, extend the database with:
- tenant identifiers,
- environment identifiers,
- cluster registry table,
- resource inventory snapshots,
- optimization recommendations,
- user audit tables,
- job execution history,
- alert history,
- data retention metadata.

## Indexing guidance
Add indexes for:
- `cost_records.subscription_id`,
- `cost_records.created_at`,
- `k8s_utilization.cluster_name`,
- `k8s_utilization.recorded_at`,
- `k8s_utilization.namespace`.

## Operational guidance
- Enable automated backups.
- Define restore testing procedure.
- Use SSL/TLS connections.
- Restrict network access to the application tier.
- Separate read and write roles if needed.
