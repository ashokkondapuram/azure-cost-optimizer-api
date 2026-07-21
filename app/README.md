# App — shared backend library

Python package mounted by all platform microservices. Production traffic runs through [services/](../services/README.md); this tree is the shared implementation.

## Key areas

| Path | Role |
|------|------|
| `routers/` | FastAPI route modules (costs, resources, optimize, sync, admin) |
| `resources/` | Resource type definitions (`MONITOR_PROFILE`, ARM fetch specs) |
| `optimizer/` | Recommendation rule engines and sub-engines |
| `assessment/` | Assessment catalog, property registry, fetch specs |
| `data_store/` | PostgreSQL queries for resources and enrichment |
| `azure_*.py`, `cost_*.py` | Azure APIs, cost queries, retail pricing |
| `metrics_api.py`, `monitor_metrics.py` | Metrics orchestration and Azure Monitor fetch |
| `integration_app.py` | **Single-process app for pytest** — all routers, no background workers |

## Run locally (integration / tests)

```bash
uvicorn app.integration_app:app --host 127.0.0.1 --port 8000 --reload
```

`app.main` is a deprecated shim that re-exports `integration_app`.

## Adding a resource type

1. Add module under `resources/{category}/`
2. Register in `resources/registry.py`
3. Add thresholds in [data/](../data/README.md)
4. Add optimization rules under `optimizer/resource_engines/`
5. Wire frontend page in `frontend/src/config/appRegistry.js`

See [it_services/](../it_services/README.md) for the per-service package layout used by microservice resource workers.
