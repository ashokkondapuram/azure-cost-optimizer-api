# Platform inventory

Resource inventory, sync orchestration, dashboard aggregates, and Azure subscription helpers.

- **Port:** 8012
- **Routes:** `/resources`, `/sync`, `/dashboard`, `/azure`

## Run

```bash
uvicorn services.platform-inventory.src.main:app --host 127.0.0.1 --port 8012
```

## Parent

[services/](../README.md)
