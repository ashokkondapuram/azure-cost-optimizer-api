# IT services (frontend)

Every resource has a folder under `it-services/<service-id>/` (see repo `it-services/catalog.json`).

| Path | Purpose |
|------|---------|
| `<service-id>/` | Service-owned React (drawer, list helpers, styles) |
| `_shared/` | Shared matchers used by service stubs |
| `registry.js` | Platform hook — only services with `drawer_ui: true` |

To add drawer UI for a service: implement in `<service-id>/`, set `drawer_ui: true` in manifest, add to `registry.enabled.json`.
