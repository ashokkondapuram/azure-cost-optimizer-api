# Docker — local stack

Runs PostgreSQL, platform microservices, and the React frontend on localhost only.

## Quick start

```bash
cp .env.example .env
cp desktop/.env.example desktop/.env   # if needed
./build.sh up
```

- **Frontend:** http://127.0.0.1:3000
- **Gateway:** http://127.0.0.1:8080

## Key files

| File | Role |
|------|------|
| `build.sh` | Up/down/logs/restart helper |
| `desktop/docker-compose.yml` | Main Desktop stack |
| `.env.example` | Stack-wide env (Postgres, auth, workers) |
| `desktop/postgres/init/` | DB init SQL (extensions, pricing seed) |
| `desktop/frontend/` | Nginx prod image + dev proxy overrides |

## Profiles

Set `COMPOSE_PROFILES` in `docker/.env`:

- `dev` — platform services + React dev server (default)
- `prod` — nginx frontend + gateway

## Common commands

```bash
./build.sh up          # start stack
./build.sh down        # stop
./build.sh logs        # tail logs
./build.sh restart     # rebuild + restart
```

## Parent

[Repository root](../README.md) · [services/](../services/README.md)
