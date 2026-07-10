# Microservices migration status

## Current state (Phase 2 complete)

- **42** per-resource services scaffolded under `services/resources/`
- **2** pilots fully migrated via gateway: `compute-disk`, `security-keyvault`
- **Platform services**: gateway, auth, cost, orchestrator
- **Monolith** (`app/`) remains for SPA static files, unmigrated resource APIs, and shared DB logic

## Runtime routing

| Request | Handler |
|---------|---------|
| `/api/resources/disks` | `compute-disk` microservice |
| `/api/resources/keyvaults` | `security-keyvault` microservice |
| Other `/api/resources/*` | Monolith (strangler fallback) |
| `/api/auth/*` | `platform-auth` (via gateway) or monolith |
| `/api/costs/*` | `platform-cost` (via gateway) or monolith |
| `/api/optimize/*` | `platform-orchestrator` (via gateway) or monolith |

Set `MICROSERVICES_ENABLED=0` to disable gateway routing hints in `app/microservices.py`.

## Decommission checklist (Phase 6)

1. Mark all services `migrated: true` in `packages/costoptimizer-core/costoptimizer_core/registry.py`
2. Run parity test suite across all resource types
3. Move SPA static hosting to `platform-gateway`
4. Remove duplicate inventory routes from `app/routers/resources_inventory.py`
5. Retain `app/` as shared library only (or merge into `costoptimizer-core`)

## Enable additional resource services

1. Add service id to `MIGRATED_SERVICES` in `registry.py`
2. Regenerate: `python3 scripts/scaffold-resource-service.py --registry-only`
3. Deploy the service container and add to `docker-compose.microservices.yml`
