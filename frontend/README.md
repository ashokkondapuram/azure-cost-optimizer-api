# Frontend — React UI

Single-page app for dashboards, resource inventory, cost explorer, recommendations, and subscription management.

## Requirements

- Node.js 22+

## Commands

```bash
npm install
npm start          # http://127.0.0.1:3000 — proxies /api to gateway :8080
npm test
npm run build      # production bundle → build/
npm run lint
```

`prestart`, `prebuild`, and `pretest` run `sync:service-display-defaults` to keep service labels in sync with backend config.

## Layout

| Path | Role |
|------|------|
| `src/App.js` | Routes and shell |
| `src/config/appRegistry.js` | Page → route → API path mapping |
| `src/api/` | Axios clients for backend endpoints |
| `src/components/` | Shared UI (drawers, cost explorer, dashboard, recommendations) |
| `src/pages/` | Top-level views |
| `public/`, `icons/` | Static assets and Azure icon set |

## API proxy

Development uses `src/setupProxy.js` (Docker overrides via `docker/desktop/frontend/setupProxy.docker.js`). All API calls go to `/api/*`, stripped and forwarded to the platform gateway.

## Parent

[Repository root](../README.md)
