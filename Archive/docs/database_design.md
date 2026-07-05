# Database Design

## Overview

All Azure data is stored locally in the database and served to the frontend from there.  
Azure APIs are only called during a **sync** operation, never per page-load.

```
Frontend  →  FastAPI  →  DB (SQLite dev / Postgres prod)
                              ↑ sync
                          Azure ARM + Cost Management APIs
```

---

## Tables

### `subscription_cache`
Caches Azure subscription list. PK = `subscription_id`.

### `resource_snapshots`
Universal resource table — every Azure resource type lives here.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `subscription_id` | String | indexed |
| `resource_id` | String | ARM resource ID |
| `resource_type` | String | `compute/vm`, `storage/account`, etc. |
| `resource_group` | String | |
| `sku` | String | VM size, storage tier, etc. |
| `state` | String | running / stopped / etc. |
| `tags_json` | Text | JSON |
| `properties_json` | Text | JSON subset of ARM properties |
| `monthly_cost_usd` | Float | last known cost |
| `is_active` | Boolean | False = deleted from Azure |
| `synced_at` | DateTime | last sync timestamp |

**Composite indexes:**
- `(subscription_id, resource_type, is_active)` — all list queries
- `(subscription_id, synced_at)` — freshness checks
- `(resource_id)` — point lookups

### `cost_snapshots`
Daily cost roll-ups per subscription + resource group.

Unique constraint on `(subscription_id, cost_date, granularity, resource_group)` makes syncs idempotent.

### `cost_by_service`
MTD cost aggregated by Azure service name. One row per `(subscription_id, service_name, month)`.

### `budget_snapshots`
Azure budget definitions + current spend.

### `optimization_runs`
Each engine analysis run with finding counts and total savings.

### `optimization_findings`
Individual findings with status tracking (open / acknowledged / resolved / ignored).

---

## Resource Type Canonical Values

| Azure Resource | `resource_type` value |
|---|---|
| Virtual Machines | `compute/vm` |
| Managed Disks | `compute/disk` |
| AKS Clusters | `containers/aks` |
| Container Registries | `containers/acr` |
| Storage Accounts | `storage/account` |
| Public IPs | `network/publicip` |
| Load Balancers | `network/loadbalancer` |
| App Gateways | `network/appgateway` |
| Network Security Groups | `network/nsg` |
| SQL Servers | `database/sql` |
| Cosmos DB | `database/cosmosdb` |
| PostgreSQL | `database/postgresql` |
| App / Function Services | `appservice/webapp` |
| Key Vaults | `security/keyvault` |

---

## Sync

Call `POST /api/resources/sync?subscription_id=<id>` to pull from Azure and populate the DB.

Recommended schedule: every 15–60 minutes via cron or Azure Function timer trigger.

```bash
curl -X POST "http://localhost:8000/api/resources/sync?subscription_id=YOUR_SUB_ID"
```

## Performance

- SQLite (dev): WAL mode + 64 MB page cache + `PRAGMA synchronous=NORMAL`
- Postgres (prod): set `DATABASE_URL=postgresql://...` in `.env`
- All hot-path columns are indexed
- Unique constraints make repeated syncs idempotent (no duplicate rows)
- `is_active=False` soft-deletes keep history without large DELETE operations
