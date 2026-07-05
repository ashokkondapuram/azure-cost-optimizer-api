# Frontend

## Overview
The frontend is a React SPA served from the FastAPI backend. It uses React Router, TanStack Query, and a registry-driven navigation model (`frontend/src/config/appRegistry.js`).

## Primary views

| Route | Component | Purpose |
|-------|-----------|---------|
| `/` | `Dashboard.jsx` | Cost/optimization portal, inventory counts, sync freshness |
| `/costs` | `CostExplorer.jsx` | MTD spend, daily trend, service breakdown |
| `/recommendations` | `Recommendations.jsx` | Findings list/grouped by resource, CSV export |
| `/k8s` | `K8sSnapshots.jsx` | Cluster utilization snapshots from the agent |
| `/history` | `RunHistory.jsx` | Optimization run history |
| Resource routes | `ResourceList.jsx`, `VirtualMachines.jsx`, `AKSClusters.jsx` | DB-first inventory with insight drawer |

Admin-only: Optimization center, Engine rules, Settings, API explorer.

## Architecture

- **Shell:** `App.js` — auth, subscription picker, currency toggle, sidebar nav
- **API:** `api/azure.js` — Axios client with bearer token
- **Registry:** `appRegistry.js` — nav groups, dashboard sections, resource page metadata
- **Findings:** `useFindingsIndex` + `indexReady` guard to avoid phantom badge counts
- **Sync:** `OperationProgressContext` + `useResourceSync` / `useCostSync`

## Data flow

1. User signs in (JWT in localStorage; httpOnly cookie migration is a future hardening item).
2. Subscription is persisted in local storage and sent on every API call.
3. List pages read synced DB inventory by default; admins can use `source=live` for ARM.
4. Findings index loads separately; inventory still renders if the index fails.

## Conventions

- Use `formatCurrency`, `formatDate`, etc. from `utils/format.js` for display text.
- Resource pages share `ResourceInventoryShell`, `FilterBar`, and `ResourceInsightDrawer`.
- Icons resolve through `config/azureIconRegistry.js`.

See also: [api-reference.md](./api-reference.md), [FUNCTIONALITY.md](./FUNCTIONALITY.md).
