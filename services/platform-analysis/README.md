# Platform analysis

Optimization engine, recommendation pipeline, analysis jobs, and event stream.

- **Port:** 8013
- **Routes:** `/optimize`, `/engine`, `/pipeline`, `/events`

## Run

```bash
uvicorn services.platform-analysis.src.main:app --host 127.0.0.1 --port 8013
```

## Parent

[services/](../README.md)
