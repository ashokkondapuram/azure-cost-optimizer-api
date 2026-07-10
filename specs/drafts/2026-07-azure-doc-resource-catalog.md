# Azure documentation–driven resource catalog rollout

**Status:** Draft  
**Date:** Jul 9, 2026  
**Pilot:** `compute/disk` (complete)

## Goal

For every IT service resource, align with official Azure documentation only:

- ARM inventory properties (`TECHNICAL_FETCH_SPEC`)
- Azure Monitor metrics (`MONITOR_PROFILE` ⊆ Learn supported-metrics)
- Optimization thresholds JSON (`metrics_required`, thresholds, doc links)
- Drawer UI (properties + live usage + associations)
- Rules catalog (no metrics that are not documented for that ARM type)

## Process per resource

1. Add `data/azure_monitor_reference/<canonical-type>.json` from Learn metrics page
2. Add `data/azure_arm_reference/<canonical-type>-get.json` from Disks/VM GET REST API where needed
3. Run `python3 scripts/audit-azure-monitor-profiles.py` — fix undocumented profile metrics
3. Update `it_services/*/resource_profile.py`
4. Update `it_services/*/data/*_metrics_thresholds.json` — disable rules when metrics are not on resource type; document alternate source
5. Implement drawer UI (`drawer_ui: true` in `it-services/*/manifest.yaml`)
6. Tests + fast suite

## Rollout queue

| Priority | Canonical type | Doc reference | Drawer UI | Audit ref |
|----------|----------------|---------------|-----------|-----------|
| 1 | compute/disk | microsoft-compute-disks-metrics | Yes | Yes |
| 2 | compute/vm | microsoft-compute-virtualmachines-metrics | Pending | Yes |
| 3 | compute/vmss | microsoft-compute-virtualmachinescalesets-metrics | Pending | No |
| 4 | compute/snapshot | microsoft-compute-snapshots-metrics | Pending | No |
| 5 | storage/account | microsoft-storage-storageaccounts-metrics | Pending | No |
| … | (see `data/azure_monitor_reference/index.json`) | | | |

## Rules that span resource types

Some optimizations require metrics from a **different** ARM type (documented, not assumed):

| Rule | Needs metric on | Not available on |
|------|-----------------|------------------|
| DISK_QUEUE_DEPTH_EXTENDED | VM OS/Data Disk Queue Depth | microsoft.compute/disks |
| DISK_CAPACITY_RIGHTSIZE_EXTENDED | Guest OS free space (VM Insights) | microsoft.compute/disks |

These rules are **disabled** in disk thresholds JSON until evaluated from the correct resource context.

## Acceptance criteria

- [ ] `audit-azure-monitor-profiles.py` exits 0 for all resources with reference files
- [ ] Every `metrics_required` entry maps to a documented REST API metric or is empty with `metrics_unavailable_reason`
- [ ] Drawer shows properties + usage for each resource with `drawer_ui: true`
- [ ] No assumed metric names in profiles (CI gate via audit script)
