# costoptimizer-core

Shared library for CostOptimizeRecommender microservices:

- **registry** — canonical type → service id, api slug, port
- **contracts** — standard `/v1` request/response models
- **resource_app** — FastAPI factory for per-resource services
- **http** — service client utilities

Install in development:

```bash
pip install -e packages/costoptimizer-core
```

Resource and platform services add the repository root to `PYTHONPATH` so existing `app/` modules remain available during the strangler migration.
