# Platform metrics

Azure Monitor metrics fetch, persistence, and per-resource metric APIs.

- **Port:** 8014
- **Routes:** `/metrics`

## Run

```bash
uvicorn services.platform-metrics.src.main:app --host 127.0.0.1 --port 8014
```

## Parent

[services/](../README.md)
