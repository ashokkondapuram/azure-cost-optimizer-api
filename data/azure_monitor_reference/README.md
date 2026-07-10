# Azure Monitor metrics reference

Curated from official Microsoft Learn supported-metrics pages. Used by
`scripts/audit-azure-monitor-profiles.py` to verify `MONITOR_PROFILE` metrics
and optimization `metrics_required` entries — nothing assumed.

## Layout

- `index.json` — all IT services, doc URLs, audit status
- `<canonical-type>.json` — documented metrics + profile fetch mapping

## Rollout order

1. compute/disk — **done** (drawer UI + doc-aligned profile)
2. compute/vm — in progress
3. compute/vmss
4. Remaining 39 services (see `index.json`)

## Updating a resource

1. Copy metrics table from Learn `supported-metrics/<arm-type>-metrics`
2. Add or refresh `<canonical-type>.json`
3. Align `it_services/*/resource_profile.py` `MONITOR_PROFILE`
4. Align `it_services/*/data/*_metrics_thresholds.json` `metrics_required`
5. Run `python3 scripts/audit-azure-monitor-profiles.py`
6. Add drawer UI (`drawer_ui: true` in manifest) when ready
