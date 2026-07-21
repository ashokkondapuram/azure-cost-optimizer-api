# Resource microservices

One FastAPI service per Azure resource type (e.g. `compute-disk`, `compute-vm`). Each worker wraps the matching [it_services/](../../it_services/README.md) package.

## Layout (per service)

```
services/resources/<service-id>/
  Dockerfile
  pyproject.toml
  src/service_app.py      # FastAPI entry
  tests/                  # Contract tests
```

Generated compose: `docker-compose.services.generated.yml`

## Pattern

- Gateway routes resource-specific calls to the appropriate worker
- Workers share `app/` and `data/` via Docker bind mounts in dev
- Contract tests: `tests/test_<service>_contract.py` in each folder

## Parent

[services/](../README.md)
