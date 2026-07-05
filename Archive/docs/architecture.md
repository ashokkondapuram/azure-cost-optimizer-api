# Architecture

## Objective
The platform provides a centralized operational application that combines Azure cost retrieval, Azure resource inventory, Kubernetes utilization collection, and historical persistence into a single full-stack system.

## High-level components

### 1. React frontend
The frontend provides the operator interface. It collects the Azure subscription identifier from the user, invokes backend APIs, and renders cost charts, resource tables, Kubernetes metrics, and historical records.

### 2. FastAPI backend
The backend acts as the orchestration and integration layer. It authenticates to Azure using Managed Identity, calls Azure control-plane APIs, processes response payloads, and stores selected operational data in PostgreSQL.

### 3. PostgreSQL database
The database stores cost query records and Kubernetes utilization snapshots. PostgreSQL provides durable persistence and can later be extended for tenancy, user preferences, optimization recommendations, and reporting aggregates.

### 4. Kubernetes utilization agent
The Kubernetes polling agent runs as a lightweight pod and gathers node and pod resource usage from the Kubernetes metrics API. It forwards that data to the backend at a configurable interval.

### 5. Azure platform dependencies
The application expects:
- Azure Web App or equivalent hosting for the backend,
- PostgreSQL database created externally,
- Managed Identity enabled on the backend host,
- Azure RBAC assigned to the Managed Identity,
- metrics-server installed in Kubernetes clusters where telemetry is collected.

## Request flow

### Cost request flow
1. User enters a subscription ID in the frontend.
2. Frontend calls backend `/costs` endpoint.
3. Backend obtains an Azure access token using Managed Identity.
4. Backend calls Azure Cost Management query API.
5. Backend stores metadata / raw response as configured.
6. Backend returns data to the frontend.
7. Frontend renders chart and summary.

### Resource inventory flow
1. User selects a resource category.
2. Frontend calls the corresponding `/resources/*` endpoint.
3. Backend authenticates with Azure ARM.
4. Backend fetches resource metadata.
5. Frontend renders the table view.

### Kubernetes telemetry flow
1. Agent polls metrics API.
2. Agent formats node and pod usage records.
3. Agent posts the data to `/k8s/utilization`.
4. Backend writes the records into PostgreSQL.
5. Frontend reads `/k8s/utilization` and renders the latest entries.

## Design principles
- Identity-based access, not secrets-based application auth.
- Least privilege RBAC.
- Lightweight Kubernetes collection rather than full observability dependency.
- Clear module boundaries.
- Manual infrastructure compatibility.
- Extensibility for enterprise-grade productization.

## Production evolution path
For large-enterprise adoption, the platform should evolve toward:
- tenant-aware architecture,
- authentication and authorization layer,
- optimization recommendations engine,
- asynchronous job execution,
- caching layer,
- richer reporting schema,
- CI/CD and release governance,
- stronger auditability.
