# Engine Extension — App Service, Redis, NAT Gateway, NICs

**Status:** Draft  
**Date:** Jun 23, 2025  
**Author:** Platform team

## Problem statement

The optimization engine covers core compute, Kubernetes, storage, and networking but misses common Azure waste patterns: empty App Service Plans, failed Redis caches, idle NAT Gateways, and unattached NICs. The extended engine produces richer findings (confidence, priority, evidence) that are not persisted or exposed in the run workflow UI.

## Proposed solution

1. Add resource fetchers and rules for App Service Plans, Redis, NAT Gateways, and NICs.
2. Fix analysis pipeline to fetch SQL databases and pass new resource types to both engines.
3. Persist extended finding metadata in PostgreSQL.
4. Expose engine version and analysis options in the Dashboard; fix Engine Config threshold editing.

## API changes

- `POST /optimize/analyze` — fetches additional resource types; persists extended fields.
- `GET /optimize/findings` — returns `confidence_score`, `action_priority`, `impact`, `evidence`, `annualized_savings_usd`.
- `GET /optimize/runs` — returns `engine_version`.
- New list endpoints: `/resources/natgateways`, `/resources/redis`, `/resources/nics`.

## Acceptance criteria

- [x] Analysis detects unattached NICs, idle NAT Gateways, failed Redis, empty App Service Plans.
- [x] Extended engine findings persist confidence, priority, evidence to DB.
- [x] Dashboard lets user choose standard vs extended engine and include metrics.
- [x] Engine Config shows and saves threshold overrides per rule.
- [x] SQL databases are fetched and evaluated in extended analysis.

## Out of scope

- Scheduled/background analysis jobs
- PDF/CSV export
- Entra ID authentication
