# Azure Cost Optimizer Platform

Enterprise-ready full-stack platform for Azure cost visibility, resource inventory, and Kubernetes utilization telemetry.

This repository contains a production-oriented application designed to help organizations collect Azure cost data, inventory Azure resources, track Kubernetes node and pod utilization, persist operational data in PostgreSQL, and present the results through a React frontend.

## Business purpose

The platform is intended for organizations that need:
- centralized Azure cost visibility,
- inventory coverage across major Azure resource types,
- a lightweight Kubernetes utilization collector,
- secure identity-based access with Managed Identity,
- data persistence for historical reporting,
- a frontend that can be adapted into an internal FinOps or platform engineering portal.

## What is included

### Backend
- Python FastAPI application.
- Azure Cost Management API integration.
- Azure Resource Manager inventory endpoints.
- PostgreSQL persistence for cost history and Kubernetes telemetry.
- CORS support for frontend integration.
- Health endpoint for operational checks.

### Frontend
- React application with a left navigation layout.
- Dashboard for Azure cost retrieval and visualization.
- Resource explorer for Azure inventory.
- Kubernetes telemetry viewer.
- Historical cost request viewer.

### Kubernetes agent
- Lightweight in-cluster polling agent.
- Reads node and pod usage from `metrics-server`.
- Pushes utilization snapshots to the backend.

## Repository map

```text
azure-cost-optimizer-api/
├── app/
│   ├── main.py
│   ├── azure_cost.py
│   ├── azure_resources.py
│   ├── database.py
│   └── models.py
├── frontend/
│   ├── package.json
│   └── src/
├── k8s/
│   ├── utilization-agent.yaml
│   └── agent.py
├── docs/
│   ├── README.md
│   ├── architecture.md
│   ├── backend.md
│   ├── frontend.md
│   ├── api-reference.md
│   ├── database.md
│   ├── security.md
│   ├── operations.md
│   ├── kubernetes-agent.md
│   ├── deployment-manual.md
│   └── production-readiness.md
└── requirements.txt
```

## Core capabilities

### 1. Azure cost retrieval
The backend queries Azure Cost Management APIs using Managed Identity through `DefaultAzureCredential`. The application supports subscription-level and resource-group-level cost retrieval and stores request history in PostgreSQL.

### 2. Azure resource inventory
The backend exposes endpoints to enumerate common Azure resource types such as Virtual Machines, AKS clusters, Storage Accounts, App Services, SQL Servers, Managed Disks, Key Vaults, Public IPs, Resource Groups, and the complete ARM resource list.

### 3. Kubernetes telemetry
A lightweight pod collects node and pod utilization from `metrics.k8s.io` and sends snapshots to the API. This gives the frontend a simple operational view without requiring a heavy observability stack.

### 4. Historical persistence
The application persists cost query metadata and Kubernetes utilization snapshots into PostgreSQL so operators can retain an audit trail and build dashboards over time.

### 5. Frontend UX
The React user interface provides navigation and views for cost data, resources, Kubernetes utilization, and cost query history.

## Intended production model

This repository now excludes infrastructure provisioning because you plan to create the Azure Web App and PostgreSQL manually. The application therefore focuses on:
- application code,
- documentation,
- runtime configuration,
- security posture,
- operational guidance,
- production-readiness expectations.

## Minimum required Azure roles

Assign the Web App Managed Identity the smallest possible set of roles:
- `Cost Management Reader` for cost data.
- `Reader` for Azure Resource Manager inventory.

Apply these roles at the subscription scope only if cross-resource visibility is required. If your operating model allows narrower scope, reduce permissions accordingly.

## Runtime configuration

### Backend environment variables
- `DATABASE_URL` - PostgreSQL SQLAlchemy connection string.
- `CORS_ALLOWED_ORIGINS` - comma-separated list of allowed frontend origins.
- `APP_ENV` - environment label such as `dev`, `qa`, or `prod`.
- `LOG_LEVEL` - logging verbosity such as `INFO` or `WARNING`.
- `REQUEST_TIMEOUT_SECONDS` - timeout for Azure REST calls.

### Frontend environment variables
- `REACT_APP_API_URL` - base URL for the backend API.

## Production expectations

For enterprise rollout, implement the following before external customer delivery:
- Azure AD or equivalent authentication in front of the frontend and backend.
- Role-based authorization for API endpoints.
- Structured logging and centralized log shipping.
- Database migration management.
- Health probes and readiness checks.
- Strong secret handling through Azure Key Vault or App Settings references.
- WAF / reverse proxy / ingress controls.
- Backup and restore procedures for PostgreSQL.
- CI/CD with quality gates.
- Audit logging and alerting.

## Reading guide

Start with these documents:
1. `docs/README.md` for documentation index.
2. `docs/architecture.md` for system design.
3. `docs/backend.md` for backend design.
4. `docs/frontend.md` for frontend structure.
5. `docs/security.md` for security posture.
6. `docs/production-readiness.md` for enterprise hardening checklist.

## License

Internal / to be decided by the product owner.
