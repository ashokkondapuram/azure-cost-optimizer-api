# Data — configuration and reference files

JSON configuration consumed at runtime by the optimizer, metrics pipeline, and assessment engine. **Do not delete assessment or threshold files** — they drive rule behavior.

## Contents

| Pattern | Purpose |
|---------|---------|
| `*_metrics_thresholds.json` | Per-service utilization thresholds and tier specs |
| `*-assessment.json` | Assessment rule definitions per resource type |
| `rule_evidence_contracts.json` | Evidence field contracts for findings |
| `azure_arm_reference/` | ARM OpenAPI snippets for property sync |
| `azure_monitor_reference/` | Monitor metric metadata |

## Usage

- Mounted read-only in Docker at `/app/data`
- Loaded by `app/service_thresholds.py`, `app/assessment/`, and resource modules
- Frontend reads a subset via bind mount for display defaults sync

## Editing thresholds

1. Edit the relevant `*_metrics_thresholds.json`
2. Restart backend services (or `./docker/build.sh restart`)
3. Re-run analysis to verify recommendation changes

Validate assessment JSON:

```bash
python3 data/validate_assessments.py
```

## Parent

[Repository root](../README.md)
