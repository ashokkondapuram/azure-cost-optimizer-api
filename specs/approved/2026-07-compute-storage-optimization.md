# Azure Compute, Containers, App Services & Storage Optimization

**Status:** Approved  
**Date:** Jul 7, 2026  
**Author:** Cost Optimize Recommender team

## Problem statement

Compute, container, app service, and storage resources represent the majority of Azure spend but lack consistent, metrics-driven optimization thresholds aligned with Azure documentation. Analysis needs catalog-backed thresholds, expanded Monitor metrics, and advisory findings ranked by priority and savings.

## Proposed solution

Implement in three batches:

1. **Compute batch** — VMs, VMSS, managed disks, disk snapshots  
2. **Containers batch** — AKS clusters, container registries  
3. **App & storage batch** — Web/function apps, app service plans, storage accounts  

Per resource:

- JSON specifications for optimization thresholds and pricing references  
- Catalog loader module  
- `optimization_rules.py` evaluators wired into existing `analysis.py`  
- Expanded `MONITOR_PROFILE` metrics and derived facts  
- Registration in rule catalog, advanced rules, evidence specs, and metrics triggers  

## Decisions

| Topic | Decision |
|-------|----------|
| Metrics source | Live Azure Monitor |
| Pricing | Azure retail, regional variance supported |
| Ranking | P1 → P3, then absolute savings |
| Automation | Advisory only (no auto-delete/archive) |
| Right-sizing CPU | Downsize &lt; 20% sustained; upsize &gt; 80% sustained |
| Reserved instances | Include 1-year and 3-year comparison in commitment rules |

## Acceptance criteria

- [ ] Nine JSON specification files under `data/`  
- [ ] Nine catalog loaders under `app/`  
- [ ] New metric-driven extended rules for each resource category  
- [ ] Monitor profiles include disk, network, and egress metrics where applicable  
- [ ] Tests cover catalog loaders and representative rule evaluators  
- [ ] Findings include structured evidence with threshold checks  

## Out of scope

- Auto-remediation or policy enforcement  
- Cross-subscription consolidation  
- Azure Advisor replacement  
