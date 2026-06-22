# API Reference

## General notes
- Base URL depends on the environment where the backend is deployed.
- All endpoints currently return JSON.
- Authentication is not yet enforced in the sample implementation and must be added before production use.

## Health

### GET /health
Purpose: simple liveness indicator.

Response example:
```json
{ "status": "ok" }
```

## Cost APIs

### GET /costs
Purpose: retrieve subscription-level Azure cost data.

Query parameters:
- `subscription_id` - required Azure subscription ID.
- `timeframe` - optional, default `MonthToDate`.
- `granularity` - optional, default `Daily`.

Behavior:
- queries Azure Cost Management,
- stores a cost record in PostgreSQL,
- returns the Azure response payload.

### GET /costs/resource-group
Purpose: retrieve resource-group-level Azure cost data.

Query parameters:
- `subscription_id` - required.
- `resource_group` - required.
- `timeframe` - optional.
- `granularity` - optional.

### GET /costs/history
Purpose: return the latest persisted cost query records.

## Resource inventory APIs

### GET /resources/all
Returns all ARM resources for the given subscription.

### GET /resources/vms
Returns virtual machines.

### GET /resources/storage
Returns storage accounts.

### GET /resources/aks
Returns AKS clusters.

### GET /resources/appservices
Returns App Services / Web Apps.

### GET /resources/sql
Returns SQL servers.

### GET /resources/disks
Returns managed disks.

### GET /resources/keyvaults
Returns Key Vaults.

### GET /resources/publicips
Returns public IP addresses.

### GET /resources/resourcegroups
Returns resource groups.

Common query parameter:
- `subscription_id` - required.

## Kubernetes telemetry APIs

### POST /k8s/utilization
Purpose: ingest a Kubernetes utilization snapshot.

Payload fields:
- `cluster_name`
- `node_name`
- `pod_name`
- `namespace`
- `cpu_usage`
- `memory_usage`

### GET /k8s/utilization
Purpose: retrieve the latest persisted Kubernetes utilization records.

## Production API recommendations
- add OpenAPI tags and descriptions,
- add authentication requirements,
- add pagination for resource endpoints,
- add filtering support,
- add versioning strategy such as `/api/v1/...`,
- add standardized error model.
