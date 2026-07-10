#!/usr/bin/env bash
# Start microservices stack for local development (gateway + pilots + monolith fallback).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="${ROOT}:${ROOT}/packages/costoptimizer-core${PYTHONPATH:+:$PYTHONPATH}"
export MICROSERVICES_ENABLED=1
export MONOLITH_URL="${MONOLITH_URL:-http://127.0.0.1:8000}"
export GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:8080}"

pip install -q -e packages/costoptimizer-core

python3 scripts/scaffold-resource-service.py --registry-only

echo "Starting platform-gateway on ${GATEWAY_URL} (monolith fallback: ${MONOLITH_URL})"
cd services/platform-gateway/src
exec uvicorn main:app \
  --host 127.0.0.1 \
  --port "${PORT:-8080}" \
  --reload
