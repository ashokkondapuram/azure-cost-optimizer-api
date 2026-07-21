#!/bin/sh
set -e

export REPO_ROOT="${REPO_ROOT:-/app}"
cd "${REPO_ROOT}"

if [ -n "${DATABASE_URL:-}" ]; then
  echo "Waiting for PostgreSQL..."
  python - <<'PY'
import os, sys, time
from urllib.parse import urlparse

url = os.environ.get("DATABASE_URL", "")
parsed = urlparse(url.replace("postgresql://", "postgres://", 1))
host = parsed.hostname or "postgres"
port = parsed.port or 5432
user = parsed.username or "costoptimizer"
db = (parsed.path or "/costoptimizer").lstrip("/").split("?")[0]

deadline = time.time() + 120
while time.time() < deadline:
    try:
        import socket
        with socket.create_connection((host, port), timeout=2):
            break
    except OSError:
        time.sleep(1)
else:
    print(f"Timed out waiting for PostgreSQL at {host}:{port}", file=sys.stderr)
    sys.exit(1)
PY
fi

if [ "${RUN_DB_INIT:-true}" = "true" ]; then
  echo "Running database schema bootstrap..."
  python -c "from app.database import init_db; init_db()"
fi

exec "$@"
