# Platform cost

Cost explorer, billing queries, budgets, and cost anomaly detection.

- **Port:** 8011
- **Routes:** `/costs`, `/cost`, `/budgets`, `/anomalies`

## Run

```bash
uvicorn services.platform-cost.src.main:app --host 127.0.0.1 --port 8011
```

## Parent

[services/](../README.md)
