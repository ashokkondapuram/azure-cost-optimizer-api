"""Azure Cost Optimizer — analysis engine sub-package.

Modules
-------
orchestrator          DB-first analysis pipeline — loads inventory, runs engines,
                      persists findings and utilization snapshots.
resource_graph        Resource dependency graph builder and action chain resolver.
anomaly_detector      Multi-method cost and utilization anomaly detection:
                      Z-score, IQR, compound zombie/idle, weekday/weekend pattern.
cross_resource_correlator
                      Cross-resource cost correlation: VM stacks, App Service Plans,
                      AKS clusters, resource groups.
cost_forecaster       OLS-based per-resource and subscription spend forecasting
                      with seasonality decomposition and CI bands.
rightsizing_confidence
                      Confidence scoring for downsize / delete recommendations:
                      observation window, utilization stability, advisor corroboration,
                      trend alignment, change-freeze awareness.
idle_pattern_detector Temporal and structural idle detection: zombie VMs, DB connection
                      drought, storage access drought, zero-invocation serverless,
                      empty AKS node pools.
"""
from app.analysis.orchestrator import (
    BUCKET_TO_TYPES,
    empty_buckets,
    load_buckets_for_keys,
    load_inventory_from_db,
    run_db_analysis,
    run_engine_on_buckets,
)

__all__ = [
    "BUCKET_TO_TYPES",
    "empty_buckets",
    "load_buckets_for_keys",
    "load_inventory_from_db",
    "run_db_analysis",
    "run_engine_on_buckets",
]
