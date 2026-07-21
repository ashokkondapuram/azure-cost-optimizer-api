#!/bin/sh
set -e

cd /app

# Named volume for node_modules persists across image rebuilds. If it was created
# before deps were installed (e.g. failed npm ci), craco will be missing until
# we repopulate node_modules here.
if [ ! -x node_modules/.bin/craco ]; then
  echo "node_modules incomplete (craco missing) — running npm ci..."
  npm ci --no-audit --no-fund
fi

exec "$@"
