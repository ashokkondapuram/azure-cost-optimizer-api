# Tests — pytest suite

Integration and unit tests for the backend. Uses `app.integration_app` (single-process FastAPI) unless testing microservice health directly.

## Run

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/

# Faster subset:
./scripts/run-fast-tests.sh

# Single file:
pytest tests/test_disk_utilization.py -v
```

## CI

`azure-pipelines.yml` runs focused pytest targets including microservice health checks.

## Conventions

- `auth_helpers.py` — shared auth fixtures
- File prefix `test_` — one module per feature area
- Mock Azure where possible; live API tests gated by env flags

## Parent

[Repository root](../README.md) · [app/](../app/README.md)
