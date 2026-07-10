# Per-Resource Microservice Architecture

**Status:** Draft (implementation in progress)  
**Date:** Jul 9, 2026  
**Author:** Cost Optimize Recommender team

## Problem statement

The platform is a modular monolith (`app/`) with 41+ Azure resource types. Teams cannot deploy, scale, or release optimization logic for one resource type without shipping the entire application. Operational blast radius and deployment coupling slow iteration.

## Proposed solution

Reorganize into a **monorepo** with:

- **`packages/costoptimizer-core`** — shared contracts, service registry, resource-service factory
- **`services/platform-*`** — gateway, auth, cost, orchestrator (single-instance platform services)
- **`services/resources/{category}-{name}`** — one deployable FastAPI service per canonical resource type

Use a **strangler-fig** migration: platform gateway routes migrated paths to microservices; unmigrated paths proxy to the monolith until Phase 6.

## Standard per-resource API contract (`/v1`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health/live` | GET | Liveness probe |
| `/v1/meta` | GET | `canonical_type`, `api_slug`, `component`, `service_id` |
| `/v1/resources` | GET | Paginated inventory (DB-first, cost overlay) |
| `/v1/resources/{resource_id}` | GET | Single resource detail |
| `/v1/sync` | POST | Scoped ARM sync for this type |
| `/v1/analyze` | POST | Run optimization for this type only |
| `/v1/rules` | GET | Rule catalog for this type |
| `/v1/metrics/collect` | POST | Fetch Azure Monitor metrics (scoped) |

## Data model

Phase 1: **shared PostgreSQL** (`resource_snapshots`, `cost_*`, `optimization_findings`). Each resource service reads/writes rows where `resource_type` matches its canonical type.

## Acceptance criteria

- [ ] `packages/costoptimizer-core` installable (`pip install -e packages/costoptimizer-core`)
- [ ] `scripts/scaffold-resource-service.py` generates a service for any canonical type
- [ ] `services/platform-gateway` proxies `/api/resources/{slug}` to migrated services or monolith
- [ ] Pilot services `compute-disk` and `security-keyvault` pass contract tests
- [ ] `platform-orchestrator` fans out analyze to migrated services
- [ ] `docker-compose.microservices.yml` starts gateway + postgres + selected services
- [ ] All 41 canonical types have scaffolded `services/resources/*` folders
- [ ] CI matrix builds changed services only
- [ ] React SPA works without route changes (API via gateway)

## Out of scope

- Per-service databases (Phase 2+)
- Auto-remediation
- Replacing Azure Cost Management with per-service cost sync

## Implementation notes

- Resource services delegate to existing `app/` modules via repo-root `PYTHONPATH` during migration.
- Cross-resource rules use `platform-orchestrator` to pass dependency context.
- Decommission monolith `app/` only after parity test suite passes.
