# Extended Optimization Engine

This module adds a more advanced analysis layer on top of the base optimizer.

## What it adds

- Confidence scoring for each recommendation.
- Action priority (`P1`, `P2`, `P3`) to help large teams execute in order.
- Annualized savings values, not only monthly values.
- Governance rules for missing tags such as `environment`, `owner`, and `costCenter`.
- Reliability-aware AKS checks so cost reduction does not break production baselines.
- Better portfolio reporting for large Azure estates with 500+ AKS clusters and 1000+ resources.

## Recommended usage

Use the existing engine for broad baseline scans, and use the extended engine when you need:

- executive-level prioritization
- higher-confidence recommendations
- governance alignment
- cost + reliability tradeoff awareness

## Files

- `app/optimizer/advanced_rules.py`
- `app/optimizer/extended_engine.py`
