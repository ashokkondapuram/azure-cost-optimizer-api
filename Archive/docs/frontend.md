# Frontend

## Overview
The frontend is a React single-page application that provides an operator-oriented interface for the platform.

## Functional views

### Dashboard
The dashboard allows the operator to request Azure cost data by subscription and timeframe. It renders a bar chart and summary statistics.

### Resources
The resources page allows the operator to browse Azure resource inventory by resource category. It presents a tabbed control that loads data from category-specific endpoints.

### Kubernetes
The Kubernetes page provides separate visibility into node-level and pod-level utilization records persisted by the backend.

### Cost history
The cost history page shows previously stored cost query records from PostgreSQL.

## Frontend architecture
The current frontend consists of:
- router shell in `App.js`,
- API abstraction layer in `api/client.js`,
- page-level components in `src/pages/`,
- global CSS in `index.css`.

## Data flow
1. The operator enters the subscription ID.
2. The frontend stores it in local storage.
3. Page components call the backend through Axios.
4. Responses are rendered in charts or tables.

## UX strengths
- simple navigation,
- low learning curve,
- fast operator workflow,
- clear separation of cost, inventory, and Kubernetes views.

## Required enterprise UX improvements
For a world-class product sold to large enterprises, add:
- Azure AD SSO,
- multi-tenant organization selector,
- role-aware menus,
- advanced filtering,
- search and pagination,
- export to CSV/PDF,
- dark mode / accessibility improvements,
- loading skeletons,
- richer empty states,
- error banners with remediation hints,
- audit views,
- saved dashboards.
