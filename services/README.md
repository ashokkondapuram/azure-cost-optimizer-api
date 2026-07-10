# Microservices layout

Per-resource FastAPI services under `resources/`, shared platform services, and `packages/costoptimizer-core`.

## Quick start (local)

```bash
pip install -e packages/costoptimizer-core
python3 scripts/scaffold-resource-service.py --registry-only

# Pilot resource services
uvicorn services.resources.compute-disk.src.main:app --host 127.0.0.1 --port 8108 &
uvicorn services.resources.security-keyvault.src.main:app --host 127.0.0.1 --port 8141 &

# Monolith fallback (SPA + unmigrated APIs)
uvicorn app.main:app --host 127.0.0.1 --port 8000 &

# Gateway
export MONOLITH_URL=http://127.0.0.1:8000
uvicorn services.platform-gateway.src.main:app --host 127.0.0.1 --port 8080
```

Or use Docker Compose:

```bash
docker compose -f docker-compose.microservices.yml up gateway
```

## Migrated services (gateway routes here first)

- `compute-disk` → `/api/resources/disks`
- `security-keyvault` → `/api/resources/keyvaults`

Regenerate all service folders:

```bash
python3 scripts/scaffold-resource-service.py --all
```

## Standard resource API

See [specs/drafts/2026-07-microservices-architecture.md](../specs/drafts/2026-07-microservices-architecture.md).
