# Extended Optimization Engine

This module adds a more advanced analysis layer on top of the base optimizer.

## What it adds

- Confidence scoring for each recommendation.
- Action priority (`P1`, `P2`, `P3`) to help large teams execute in order.
- Annualized savings values, not only monthly values.
- Rule-level summary rollups and priority summary rollups.
- Governance rules for missing tags such as `environment`, `owner`, and `costCenter`.
- Reliability-aware AKS checks so cost reduction does not break production baselines.
- Extended cleanup checks for old snapshots, idle load balancers, idle application gateways, and idle public IPs.
- Security and cost guardrails for Key Vault protection settings and Azure Budget overrun risk.
- Better portfolio reporting for large Azure estates with 500+ AKS clusters and 1000+ resources.

## Recommended usage

Use the existing engine for broad baseline scans, and use the extended engine when you need:

- executive-level prioritization
- higher-confidence recommendations
- governance alignment
- cost + reliability tradeoff awareness

## API usage

The extended engine is opt-in through the existing analysis endpoint:

```json
POST /optimize/analyze
{
  "subscription_id": "<subscription-id>",
  "profile": "default",
  "engine_version": "extended",
  "include_metrics": true,
  "timespan_metrics": "P7D"
}
```

Use `engine_version: "standard"` or omit the field to keep the original engine behavior.

## Extended output fields

Extended findings include the base fields plus:

- `annualized_savings_usd`
- `confidence_score`
- `action_priority`
- `impact`
- `evidence`

The extended summary includes:

- `total_estimated_annual_savings_usd`
- `by_priority`
- `top_rules`
- `average_confidence_score`

## Extended rule coverage

- Compute: underutilized VMs, right-sizing candidates, commitment candidates, unattached disks, stale snapshots.
- Kubernetes: idle node pools, non-production scheduling, production system-pool reliability.
- Network: idle static public IPs, empty load balancers, application gateways without listeners.
- Storage: lifecycle tiering candidates.
- Database: SQL serverless candidates and Cosmos autoscale/serverless candidates.
- Security: Key Vault soft-delete and purge-protection baseline.
- Governance: required ownership and cost-allocation tags.
- Cost: budget guardrail breach risk.

## Files

- `app/optimizer/advanced_rules.py`
- `app/optimizer/extended_engine.py`
- `app/main.py`
