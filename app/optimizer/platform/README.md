# Optimization platform (resource-independent)

Shared engine runtime and cross-cutting analysis — **not** owned by a single Azure resource.

| Path | Purpose |
|------|---------|
| `runtime/` | `ResourceSubEngine`, `AnalysisContext`, resource envelope |
| `cost/` | Budgets, commitments, cost anomalies |
| `sub_engine_registry.py` | Loads per-resource sub-engines from `it_services/*/engine/` |
| `analysis_batches.py` | Generated batch order (one batch per resource service) |

Per-resource sub-engines, analysis rules, and optimization logic live in `it_services/<service_pkg>/engine/`.
