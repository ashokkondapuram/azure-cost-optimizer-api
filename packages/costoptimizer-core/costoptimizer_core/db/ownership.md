# Database ownership (Phase 1 — shared PostgreSQL)

| Table / area | Owner | Access by resource services |
|--------------|-------|-----------------------------|
| `resource_snapshots` | Per-type write via scoped sync | Read/write rows matching `resource_type` |
| `cost_*` | `platform-cost` | Read-only |
| `optimization_findings` | `platform-orchestrator` + resource analyze | Write via analyze endpoint |
| `resource_utilization_history` | `platform-metrics` | Read; optional collect per service |
| `app_users`, `system_settings` | `platform-auth` | None |
| `analysis_jobs`, `optimization_runs` | `platform-orchestrator` | None |

Phase 2 may split databases; until then all services share `DATABASE_URL`.
