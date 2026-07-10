#!/bin/bash
# Self-contained startup — deps ship in python_packages/ from CI (no Oryx/antenv).
set -euo pipefail

ROOT="/home/site/wwwroot"
cd "${ROOT}"

export PYTHONPATH="${ROOT}/python_packages/lib/site-packages:${PYTHONPATH:-}"
export PYTHONUNBUFFERED=1

echo "=== startup.sh ==="
echo "PWD=$(pwd)"
echo "PYTHONPATH=${PYTHONPATH}"

if ! python -c "import uvicorn" 2>/dev/null; then
  echo "ERROR: uvicorn not importable."
  ls -la "${ROOT}/python_packages/lib/site-packages/uvicorn" 2>/dev/null || echo "python_packages/uvicorn missing from wwwroot"
  ls -la "${ROOT}/requirements.txt" 2>/dev/null || echo "requirements.txt missing"
  exit 1
fi

UI_INDEX="${ROOT}/frontend/build/index.html"
if [ -f "${UI_INDEX}" ]; then
  echo "UI found: ${UI_INDEX}"
else
  echo "WARN: React build missing at ${UI_INDEX}"
fi

PORT="${PORT:-8000}"
exec python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --timeout-keep-alive 75 \
  --proxy-headers \
  --forwarded-allow-ips='*'
