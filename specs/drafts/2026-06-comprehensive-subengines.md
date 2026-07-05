# Comprehensive Recommendations & Analysis Sub-Engines

**Status:** Draft  
**Date:** Jun 29, 2026  
**Author:** Platform team

## Problem statement

The extended optimization engine (default analysis path) has three coverage gaps:

1. **13 synced resource types** (Log Analytics, App Insights, APIM, Data Factory, Logic Apps, Event Hubs, Service Bus, Databricks, Synapse, ADX, ML Workspace, Recovery Vault, Cognitive Search) are synced to inventory but never loaded into analysis buckets — only cost-export spend heuristics apply.
2. **~30 standard rules** in the monolithic engine are not run when `engine_version="extended"`, leaving gaps such as AKS autoscale checks, SQL idle detection, and disk oversizing.
3. **Commitments analysis is incomplete** — `RESERVED_OPPORTUNITY` and `SAVINGS_PLAN_OPPORTUNITY` are catalog-only; subscription-level RI/Savings Plan guidance is missing.

Stub sub-engines (snapshots, Cosmos, most network types) produce one finding type each, while VM, AKS, PostgreSQL, and App Service are fully covered.

## Proposed solution

Deliver in four phases:

| Phase | Scope |
|-------|-------|
| **1** | Port high-value standard rules to extended sub-engines; add VMSS-specific analysis; fix SQL database bucket routing; enrich stub sub-engines |
| **2** | New Commitments sub-engine with subscription-level RI and Savings Plan analysis |
| **3** | Plumbing + 13 new sub-engines (Monitoring, Integration, Messaging, Analytics, Backup, Search) |
| **4** | Optional new ARM extractors for unmapped types (Firewall, CDN, MySQL, etc.) |

## Data model changes

None. Reuse existing `optimization_findings` extended fields (`confidence_score`, `action_priority`, `impact`, `evidence_json`, `annualized_savings_usd`).

## API changes

No new endpoints. New rules auto-surface via:

- `GET /optimize/rules`
- `GET /optimize/rules/by-component`
- `POST /optimize/analyze` (extended engine, default)

## UI changes

Recommendations page and detail cards automatically show new findings via existing APIs. Component filter tabs gain Monitoring, Integration, Messaging, Analytics, Backup, and Search coverage.

## Acceptance criteria

### Phase 1

- [ ] Extended engine includes ported rules: AKS (old version, autoscale, spot, single pool), disk oversize, SQL idle, Cosmos provisioned, storage hot unused, Redis failed, Key Vault soft delete
- [ ] VMSS sub-engine has ≥2 dedicated rules (autoscale, non-prod scheduling)
- [ ] SQL databases routed to `sql_databases` bucket separately from servers
- [ ] Budget extended rules include warning and critical thresholds

### Phase 2

- [ ] `CommitmentsSubEngine` registered and runs on VM bucket + subscription context
- [ ] `RESERVED_OPPORTUNITY` and `SAVINGS_PLAN_OPPORTUNITY` produce findings with evidence
- [ ] `VM_COMMITMENT_CANDIDATE` remains available under Commitments component

### Phase 3

- [ ] All 13 resource types in `TYPE_TO_BUCKET`, `empty_buckets`, `component_map`, `metrics_loader`
- [ ] Each type has a sub-engine producing ≥1 inventory-based finding when misconfigured
- [ ] Cost-export rules remain as fallback for below-threshold spend

### Phase 4

- [ ] At least Firewall and CDN/Front Door extractors added when cost data warrants

## Out of scope

- Scheduled or background analysis jobs
- PDF/CSV export of findings
- Entra ID authentication changes
- Deprecation of standard engine (future work)
- New ARM extractors until Phase 4

## Open questions

- Should subscription-level commitment findings attach to a synthetic subscription resource or the highest-spend VM?
- Priority order for Phase 4 extractors based on customer spend profiles?

## Dependencies

- Azure inventory sync for all 33 resource types
- Azure Monitor metrics for utilization-based rules
- Cost Management MTD export for savings estimates
