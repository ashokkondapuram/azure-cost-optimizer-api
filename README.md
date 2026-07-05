# InfinityOps Platform

Enterprise FinOps platform for Azure cost visibility, resource inventory, optimization recommendations, and optional Kubernetes utilization telemetry.

This repository contains a production-oriented application that collects Azure cost data, inventories Azure resources, runs a rule-based optimization engine with savings estimates, persists operational data in PostgreSQL, and presents results through a React frontend.

## Business purpose

The platform is intended for organizations that need:
- centralized Azure cost visibility and budget tracking,
- inventory coverage across major Azure resource types,
- actionable optimization recommendations grounded in actual billed cost,
- secure JWT-based authentication with role-based access (admin vs viewer),
- data persistence for historical reporting and analysis runs,
- a frontend FinOps portal for cost, inventory, and recommendations.

## What is included

### Backend
- Python FastAPI application (`app/main.py`).
- Azure Cost Management API integration (actual spend only — no list-price heuristics in user-facing cost fields).
- Azure Resource Manager inventory and live-read endpoints.
- Optimization engine with per-resource sub-engines (`app/optimizer/`).
- PostgreSQL persistence for costs, inventory snapshots, findings, and analysis jobs.
- JWT authentication, subscription scoping, and admin-gated analysis/sync operations.

### Frontend
- React SPA with navigation driven by `frontend/src/config/appRegistry.js`.
- Dashboard, cost explorer, resource inventory pages, and **Recommendations** (`/recommendations`).
- Admin tools: optimization runs, engine config, settings, user management.
- Shared findings index for consistent badges and drawer panels across resource pages.

### Kubernetes agent
- Lightweight in-cluster polling agent (`k8s/agent.py`).
- Reads node and pod usage from `metrics-server`.
- Pushes utilization snapshots to the backend (token-authenticated in production).

## Repository map

```text
CostOptimizeRecommender/
├── app/
│   ├── main.py              # FastAPI routes (costs, resources, optimize, auth)
│   ├── analysis/            # DB analysis orchestration
│   ├── dashboard/           # Dashboard API
│   ├── optimizer/           # Rule engine + resource sub-engines
│   ├── resources/           # Per-type technical fetch + metrics specs
│   └── database.py
├── frontend/
│   ├── package.json
│   └── src/
│       ├── config/appRegistry.js   # Nav + route source of truth
│       └── pages/Recommendations.jsx
├── k8s/
│   ├── utilization-agent.yaml
│   └── agent.py
├── docs/
│   ├── README.md
│   ├── FUNCTIONALITY.md
│   ├── DEPLOY_APP_SERVICE.md
│   └── ...
└── requirements.txt
```

## Core capabilities

### 1. Azure cost retrieval
The backend queries Azure Cost Management APIs using Managed Identity through `DefaultAzureCredential`. Supports subscription-level and resource-group-level cost retrieval; stores snapshots and query history in PostgreSQL.

### 2. Azure resource inventory
Endpoints enumerate VMs, disks, AKS, storage, databases, networking, App Service, Key Vault, and aggregate pages (monitoring, integration, analytics, etc.). Inventory can be synced from Azure into PostgreSQL for fast list views.

### 3. Optimization engine
Rule-based analysis (`/optimize/analyze`, admin-only) produces findings with `estimated_savings_usd` derived from **actual billed cost** baselines. Findings are listed at `/optimize/findings` and in the UI at `/recommendations`.

### 4. Kubernetes telemetry
Optional in-cluster agent collects node/pod utilization and sends snapshots to the API.

### 5. Authentication & authorization
When `AUTH_ENABLED=true` (required in production):
- JWT login at `/api/auth/login` with rate limiting.
- Protected API roots include `/dashboard`, `/sync`, `/optimize`, `/resources`, and related paths.
- Admin role required for analysis, sync-from-Azure, settings, and user management.

## Runtime configuration

### Backend environment variables (key)
- `DATABASE_URL` — PostgreSQL SQLAlchemy connection string.
- `CORS_ALLOWED_ORIGINS` — comma-separated allowed frontend origins.
- `APP_ENV` — `dev`, `qa`, or `prod`.
- `AUTH_ENABLED` — must be `true` in production.
- `JWT_SECRET` — signing key for access tokens (required when auth enabled).
- `SETTINGS_ENCRYPTION_KEY` — encrypts sensitive settings at rest (required in production).
- `K8S_AGENT_TOKEN` — shared secret for utilization agent POSTs (required in production).

### Frontend environment variables
- `REACT_APP_API_URL` — base URL for the backend API.

## Minimum required Azure roles

Assign the Web App Managed Identity:
- `Cost Management Reader` for cost data.
- `Reader` for Azure Resource Manager inventory.

Apply at subscription scope only when cross-resource visibility is required.

## Reading guide

1. `docs/FUNCTIONALITY.md` — end-to-end behavior, cost policy, routes.
2. `docs/architecture.md` — system design.
3. `docs/backend.md` — backend modules.
4. `docs/frontend.md` — frontend structure and `appRegistry`.
5. `docs/security.md` — auth, secrets, production gates.
6. `docs/DEPLOY_APP_SERVICE.md` — Azure App Service deployment.

## License

Internal / to be decided by the product owner.
