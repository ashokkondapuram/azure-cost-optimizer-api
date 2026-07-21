# Cost Optimize Recommender

Azure cost optimization platform that syncs subscription inventory, collects utilization metrics, and surfaces savings recommendations.

**Stack:** Python (FastAPI microservices), React, PostgreSQL, Azure SDK

## Quick start (Docker Desktop)

```bash
cp docker/.env.example docker/.env
./docker/build.sh up
```

- Frontend: http://127.0.0.1:3000
- API gateway: http://127.0.0.1:8080
- API docs (gateway): http://127.0.0.1:8080/docs

Copy `docker/desktop/.env.example` to `docker/desktop/.env` if compose prompts for it. `./docker/build.sh up` can create env files from examples.

## Local development (without Docker)

```bash
cp .env.example .env          # bare-metal / uvicorn
pip install -r requirements.txt -r requirements-dev.txt

# All routes in one process (tests and API smoke)
uvicorn app.integration_app:app --host 127.0.0.1 --port 8000 --reload

# Frontend
cd frontend && npm install && npm start
```

## Repository layout

| Folder | Purpose |
|--------|---------|
| [app/](app/README.md) | Shared backend library, routers, optimizer, resource definitions |
| [services/](services/README.md) | Production microservices (gateway, inventory, cost, analysis, metrics) |
| [frontend/](frontend/README.md) | React UI |
| [data/](data/README.md) | Threshold JSON, assessment specs, Azure reference data |
| [it_services/](it_services/README.md) | Per-resource Python packages (metrics, rules, SKU data) |
| [docker/](docker/README.md) | Docker Compose, build scripts, local stack |
| [tests/](tests/README.md) | Pytest suite |
| [migrations/](migrations/README.md) | SQL schema migrations |
| [design/](design/README.md) | Static UI concept prototypes |

## Tests

```bash
pytest tests/
# or focused suite:
./scripts/run-fast-tests.sh
```

## Configuration

- Root `.env.example` — bare-metal / single-process dev
- `docker/.env.example` — Docker stack (Postgres, auth, workers)
- See [docker/README.md](docker/README.md) for profiles (`dev` vs `prod`)
