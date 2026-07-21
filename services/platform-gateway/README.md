# Platform gateway

Reverse proxy and API entry point. Strips `/api` prefix and routes to platform services.

- **Port:** 8080 (Docker and local)
- **Config:** `routes.generated.yaml` — service route table

## Run

```bash
uvicorn services.platform-gateway.src.main:app --host 127.0.0.1 --port 8080
```

## Parent

[services/](../README.md)
