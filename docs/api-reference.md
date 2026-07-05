# API Reference

## General notes

- Base URL: `/api` in production (mirrored from root paths via `app/route_mirror.py`).
- All JSON responses unless noted.
- **Authentication:** JWT bearer tokens when `AUTH_ENABLED=true` (default). Sign in at `POST /auth/login`, then send `Authorization: Bearer <token>`.
- **Subscription scoping:** Most data endpoints require `subscription_id` and reject unknown subscriptions (404).
- **Admin-only:** Sync, analyze, settings, live Azure reads, engine config, and several metrics endpoints require role `admin`.

## Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | Public | Liveness |
| GET | `/health/live` | Public | Liveness probe |
| GET | `/health/ready` | Public | Readiness probe |

## Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/login` | Public | Username/password login (rate limited) |
| GET | `/auth/me` | User | Current user profile |

## Cost Management

Primary cost reads are **database-first** (blob export sync via `POST /costs/sync`). Live Cost Management calls are admin-only where noted.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/costs` | User + subscription | Daily cost series from DB |
| GET | `/costs/resource-group` | User + subscription | RG-scoped daily costs |
| GET | `/costs/by-resource` | User + subscription | Per-resource MTD costs |
| GET | `/costs/by-service` | User + subscription | Service breakdown |
| GET | `/costs/summary` | User + subscription | Summary KPIs |
| GET | `/costs/changes` | User + subscription | MTD cost deltas |
| GET | `/cost/daily` | User + subscription | Daily rollup |
| GET | `/costs/history` | User + subscription | Cost query audit log (scoped) |
| GET | `/costs/forecast` | Admin + subscription | Live forecast |
| GET | `/costs/dimensions` | Admin + subscription | Live filter dimensions |
| GET | `/costs/budgets` | User + subscription | Budgets (DB; live fallback admin) |
| POST | `/costs/sync` | Admin | Pull blob export into DB |

## Dashboard

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/dashboard/overview` | User + subscription | Dashboard KPIs |
| GET | `/sync/status` | User + subscription | Sync freshness |
| GET | `/dashboard/resources/{resource_id}` | User + subscription | Resource detail |
| GET | `/advisor/recommendations` | User + subscription | Advisor recommendations |
| GET | `/alerts/monitor` | User + subscription | Monitor alert resources |
| GET | `/outliers/underutilized` | User + subscription | Underutilized resources |
| GET | `/budgets` | User + subscription | Budget snapshots |

## Resources

DB-first list endpoints accept `source=db` (default) or `source=live` (admin). Live-only list endpoints require admin.

| Method | Path | Notes |
|--------|------|-------|
| GET | `/resources/subscriptions` | Subscription catalog |
| POST | `/resources/subscriptions/sync` | Admin — refresh catalog from Azure |
| POST | `/resources/sync` | Admin — inventory + optional cost sync |
| GET | `/resources/counts` | Counts by category |
| GET | `/resources/vms`, `/disks`, `/aks`, … | Paginated inventory (`limit`, `offset`) |
| GET | `/resources/vms/{rg}/{name}/sizing` | VM rightsizing (scoped subscription) |
| GET | `/resources/mysql`, `/vnets`, `/nics`, … | Admin live ARM reads |

See `app/main.py` and OpenAPI at `/api/openapi.json` (admin) for the full route list.

## Optimization

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/optimize/analyze` | Admin | Queue or run analysis |
| POST | `/optimize/analyze/batch` | Admin | Queue batched job |
| GET | `/optimize/jobs`, `/optimize/jobs/{id}` | User + subscription | Job status |
| GET | `/optimize/runs`, `/optimize/runs/{id}` | User + subscription | Run history |
| GET | `/optimize/findings` | User + subscription | Open/closed findings |
| GET | `/optimize/findings/summary` | User + subscription | Aggregated summary |
| PATCH | `/optimize/findings/{id}/status` | Admin + subscription | Update finding status |
| GET | `/optimize/config/{profile}` | Admin | Engine rule overrides |
| GET | `/optimize/rules` | User | Rule catalog |

## Settings (admin)

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/settings/{category}` | Azure, database, kubernetes, ai config |

## Kubernetes agent

All `/k8s/*` routes require header **`X-API-Key`** (value from `K8S_AGENT_TOKEN` or Settings → Kubernetes). JWT middleware is skipped; token is required when auth is enabled.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/k8s/utilization` | Legacy utilization payload |
| POST | `/k8s/snapshot` | Batched cluster snapshot |
| GET | `/k8s/snapshot`, `/k8s/snapshots` | Read snapshots |

## Environment variables (backend)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL (required in production) |
| `JWT_SECRET` | JWT signing (required in production) |
| `SETTINGS_ENCRYPTION_KEY` | Encrypt settings at rest (required in production) |
| `K8S_AGENT_TOKEN` | Agent API key (required in production) |
| `ADMIN_PASSWORD` | Bootstrap admin password (required in production) |
| `AUTH_ENABLED` | Must be true in production |
| `CORS_ALLOWED_ORIGINS` | Allowed frontend origins |
