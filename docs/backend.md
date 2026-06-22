# Backend

## Overview
The backend is implemented in Python using FastAPI. It acts as the system of integration between Azure APIs, PostgreSQL persistence, and the React frontend.

## Modules

### main.py
Primary application entry point. Responsibilities include:
- creating the FastAPI app,
- registering middleware,
- exposing routes,
- handling request validation,
- coordinating persistence,
- returning serialized responses.

### azure_cost.py
Encapsulates Azure Cost Management API interaction. Responsibilities include:
- acquiring ARM token through `DefaultAzureCredential`,
- constructing REST requests,
- submitting cost query payloads,
- returning raw Azure response payloads.

### azure_resources.py
Encapsulates Azure Resource Manager inventory calls. Responsibilities include listing:
- all resources,
- virtual machines,
- storage accounts,
- AKS clusters,
- app services,
- SQL servers,
- managed disks,
- key vaults,
- public IPs,
- resource groups.

### database.py
Centralizes SQLAlchemy engine and session configuration. It provides a session generator to the FastAPI dependency injection system.

### models.py
Defines ORM models for persisted entities. The current schema includes:
- `CostRecord`
- `K8sUtilization`

## Request handling model

### Synchronous flow
The current implementation uses synchronous HTTP requests to Azure. This keeps the code simple and easy to understand, but production-grade scaling may later benefit from:
- retry wrappers,
- circuit breakers,
- async clients,
- background jobs for long-running queries.

### Error handling
Routes currently wrap integration calls in broad exception handling and convert failures into HTTP 500 responses. For enterprise delivery, improve this by introducing:
- typed exception mapping,
- standardized error payloads,
- correlation IDs,
- client-safe error messages,
- retry classification.

## Persistence behavior
The backend stores:
- Azure cost query history,
- raw cost response payloads,
- Kubernetes telemetry snapshots.

This creates a base for later enterprise features such as:
- reporting dashboards,
- usage trend analysis,
- anomaly detection,
- optimization recommendation history,
- audit trails.

## Recommended production enhancements
- Add Alembic migrations and migration runbooks.
- Add Pydantic response/request schemas for every endpoint.
- Add service layer separation from route layer.
- Add structured JSON logging.
- Add request tracing.
- Add rate limiting.
- Add authentication and authorization.
- Add pagination for inventory endpoints.
- Add database retention jobs.
- Add unit, integration, and contract tests.
