#!/usr/bin/env bash
# Inspect and provision Kafka topics + Schema Registry schemas for Redpanda.
#
# Requires the costopt-redpanda container from Docker Compose for list/describe/consume.
# init/verify/schemas use Python scripts (Admin API + Schema Registry REST).
#
# Usage:
#   ./scripts/kafka-topics.sh list
#   ./scripts/kafka-topics.sh init
#   ./scripts/kafka-topics.sh verify
#   ./scripts/kafka-topics.sh schemas
#   ./scripts/kafka-topics.sh describe sync.inventory.requested
#   ./scripts/kafka-topics.sh consume sync.inventory.requested [max_messages]
#   ./scripts/kafka-topics.sh groups
#
# Environment:
#   REDPANDA_CONTAINER          Docker container name (default: costopt-redpanda)
#   REDPANDA_BROKERS            Bootstrap brokers inside container (default: redpanda:9092)
#   KAFKA_BOOTSTRAP_SERVERS     Host/bootstrap for init/verify (default: 127.0.0.1:9092)
#   KAFKA_SCHEMA_REGISTRY_URL   Schema Registry URL (default: http://127.0.0.1:18081)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REDPANDA_CONTAINER="${REDPANDA_CONTAINER:-costopt-redpanda}"
REDPANDA_BROKERS="${REDPANDA_BROKERS:-redpanda:9092}"
KAFKA_BOOTSTRAP_SERVERS="${KAFKA_BOOTSTRAP_SERVERS:-127.0.0.1:9092}"
KAFKA_SCHEMA_REGISTRY_URL="${KAFKA_SCHEMA_REGISTRY_URL:-http://127.0.0.1:18081}"

exec_in_redpanda() {
  docker exec "$REDPANDA_CONTAINER" "$@"
}

require_redpanda_container() {
  if ! docker inspect "$REDPANDA_CONTAINER" >/dev/null 2>&1; then
    echo "Redpanda container '$REDPANDA_CONTAINER' is not running." >&2
    echo "Start it with: ./docker/build.sh up  (or docker compose up redpanda)" >&2
    exit 1
  fi
}

run_init() {
  local mode="$1"
  shift
  local args=(--brokers "$KAFKA_BOOTSTRAP_SERVERS" --registry-url "$KAFKA_SCHEMA_REGISTRY_URL")
  if [[ "$mode" == "verify" ]]; then
    args+=(--verify)
  fi
  python3 "$ROOT_DIR/scripts/kafka_init.py" "${args[@]}" "$@"
}

cmd="${1:-list}"
shift || true

case "$cmd" in
  init|provision)
    run_init init
    ;;
  verify)
    run_init verify
    ;;
  schemas)
    python3 "$ROOT_DIR/scripts/kafka_schemas_register.py" \
      --registry-url "$KAFKA_SCHEMA_REGISTRY_URL" "$@"
    ;;
  schemas-verify)
    python3 "$ROOT_DIR/scripts/kafka_schemas_register.py" \
      --registry-url "$KAFKA_SCHEMA_REGISTRY_URL" --verify "$@"
    ;;
  list)
    require_redpanda_container
    rpk_brokers=(-X "brokers=$REDPANDA_BROKERS")
    exec_in_redpanda rpk topic list "${rpk_brokers[@]}"
    ;;
  describe)
    require_redpanda_container
    topic="${1:?Usage: $0 describe <topic>}"
    rpk_brokers=(-X "brokers=$REDPANDA_BROKERS")
    exec_in_redpanda rpk topic describe "$topic" "${rpk_brokers[@]}"
    ;;
  consume)
    require_redpanda_container
    topic="${1:?Usage: $0 consume <topic> [max_messages]}"
    max_messages="${2:-10}"
    rpk_brokers=(-X "brokers=$REDPANDA_BROKERS")
    exec_in_redpanda rpk topic consume "$topic" -n "$max_messages" "${rpk_brokers[@]}"
    ;;
  groups)
    require_redpanda_container
    rpk_brokers=(-X "brokers=$REDPANDA_BROKERS")
    exec_in_redpanda rpk group list "${rpk_brokers[@]}"
    ;;
  group-describe)
    require_redpanda_container
    group="${1:?Usage: $0 group-describe <group_id>}"
    rpk_brokers=(-X "brokers=$REDPANDA_BROKERS")
    exec_in_redpanda rpk group describe "$group" "${rpk_brokers[@]}"
    ;;
  *)
    echo "Usage: $0 {init|verify|schemas|schemas-verify|list|describe|consume|groups|group-describe} [args...]" >&2
    exit 1
    ;;
esac
