# IT services — per-resource Python packages

Canonical backend packages for each Azure resource type. Each folder is a self-contained module with metrics profiles, optional optimization rules, and service-owned threshold data.

## Package layout

```
it_services/<service_pkg>/
  service.py              # Public exports (generated)
  resource_profile.py     # MONITOR_PROFILE + TECHNICAL_FETCH_SPEC
  engine/                 # Sub-engine (analysis, optimization_rules)
  data/                   # sku_specs.json, service thresholds
```

**Naming:** `service_id` `compute-disk` → package `compute_disk`

## Relationship to other trees

| Layer | Location |
|-------|----------|
| Shared resource registry | `app/resources/` |
| Global thresholds | `data/*_metrics_thresholds.json` |
| Microservice workers | `services/resources/<service-id>/` |
| Frontend display | `frontend/src/config/` |

## Regenerate SKU catalogs

```bash
python3 scripts/sync-azure-sku-specs.py --fetch-retail-prices
```

## Scaffold a new service

Copy `_template/` (if present) or an existing sibling package, then register the resource in `app/resources/registry.py`.

## Parent

[Repository root](../README.md) · [app/](../app/README.md)
