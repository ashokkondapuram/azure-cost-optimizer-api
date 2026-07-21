#!/usr/bin/env bash
# Start the platform gateway for local development (microservices-only).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}/services/platform-gateway/src"

export GATEWAY_PORT="${GATEWAY_PORT:-8080}"
export CORE_SERVICE_URL="${CORE_SERVICE_URL:-http://127.0.0.1:8010}"
export INVENTORY_SERVICE_URL="${INVENTORY_SERVICE_URL:-http://127.0.0.1:8012}"
export COST_SERVICE_URL="${COST_SERVICE_URL:-http://127.0.0.1:8011}"
export ANALYSIS_SERVICE_URL="${ANALYSIS_SERVICE_URL:-http://127.0.0.1:8013}"
export METRICS_SERVICE_URL="${METRICS_SERVICE_URL:-http://127.0.0.1:8014}"
export MICROSERVICES_ONLY=1

echo "Starting platform-gateway on ${GATEWAY_PORT}"
exec uvicorn main:app \
  --host 127.0.0.1 \
  --port "${GATEWAY_PORT}" \
  --reload
