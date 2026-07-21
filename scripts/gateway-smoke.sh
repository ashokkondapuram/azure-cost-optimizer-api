#!/usr/bin/env bash
# Smoke-test platform gateway routing and async accept timing.
set -euo pipefail

GATEWAY="${GATEWAY_URL:-http://127.0.0.1:8080}"

echo "Gateway: $GATEWAY"

curl -fsS "$GATEWAY/health/live" | grep -q '"status":"ok"'

probe_route() {
  local path="$1"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' "$GATEWAY$path")"
  if [[ "$code" == "404" ]]; then
    echo "FAIL $path returned 404 (no gateway route)" >&2
    exit 1
  fi
  echo "OK   $path -> HTTP $code (routed)"
}

for path in \
  /health/live \
  /optimize/findings \
  /costs/summary \
  /metrics/profiles \
  /dashboard/overview \
  /sync/status \
  /sync/pipeline \
  /auth/me \
  /resources/disks \
  /resources/vms \
  /resources/sync; do
  probe_route "$path"
done

echo ""
echo "Accept-path timing (unauthenticated — expect fast 401/403/422, not 404/504):"

time_accept_post() {
  local path="$1"
  local start end elapsed code
  start="$(python3 -c 'import time; print(time.time())')"
  code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$GATEWAY$path?subscription_id=00000000-0000-0000-0000-000000000001&wait=false")"
  end="$(python3 -c 'import time; print(time.time())')"
  elapsed="$(python3 -c "print(int((${end} - ${start}) * 1000))")"
  if [[ "$code" == "404" ]]; then
    echo "FAIL POST $path -> HTTP $code in ${elapsed}ms (unrouted)" >&2
    exit 1
  fi
  if [[ "$code" == "504" ]]; then
    echo "FAIL POST $path -> HTTP $code in ${elapsed}ms (gateway upstream timeout)" >&2
    exit 1
  fi
  echo "OK   POST $path -> HTTP $code in ${elapsed}ms"
}

time_accept_post "/resources/sync"
time_accept_post "/resources/sync?types=database%2Fcosmosdb&include_costs=true&components=Cosmos+DB&wait=false"
time_accept_post "/sync/full"
time_accept_post "/optimize/analyze/batch"

echo ""
echo "Route table:"
curl -fsS "$GATEWAY/v1/routes" | head -c 400
echo ""
echo "Gateway smoke checks passed."
