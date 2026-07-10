#!/usr/bin/env bash
# Fast pre-push checks for IT services / engine migration work (~90 tests, ~5s).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Backend (focused subset)"
python3 -m pytest \
  tests/test_disk_analysis_config.py \
  tests/test_disk_staleness_engine.py \
  tests/test_disk_staleness.py \
  tests/test_compute_storage_optimization.py \
  tests/test_network_optimization_batch1.py \
  tests/test_network_optimization_batch23.py \
  tests/test_acr_analysis.py \
  tests/test_microservices.py \
  tests/test_advanced_analysis_improvements.py \
  tests/test_commitment_findings.py \
  tests/test_cost_live_explorer_period.py \
  -q --tb=line

echo "==> Frontend"
(cd frontend && npm test -- --watchAll=false)

echo "==> All fast checks passed"
