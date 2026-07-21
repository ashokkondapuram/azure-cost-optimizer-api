#!/usr/bin/env bash
# CostOptimizeRecommender — Docker Desktop helper
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKER_DIR="${SCRIPT_DIR}"
REPO_ROOT="$(cd "${DOCKER_DIR}/.." && pwd)"
COMPOSE_FILE="${DOCKER_DIR}/desktop/docker-compose.yml"
COMPOSE_PROJECT_NAME="costoptimize-desktop"
ENV_FILE="${DOCKER_DIR}/.env"
ENV_EXAMPLE="${DOCKER_DIR}/.env.example"
DESKTOP_ENV_FILE="${DOCKER_DIR}/desktop/.env"
DESKTOP_ENV_EXAMPLE="${DOCKER_DIR}/desktop/.env.example"

# BuildKit + parallel bake (Compose 2.23+) — layer cache and faster multi-service builds
export DOCKER_BUILDKIT="${DOCKER_BUILDKIT:-1}"
export COMPOSE_BAKE="${COMPOSE_BAKE:-true}"

read_env_value() {
  local key="$1" file="$2"
  [[ -f "${file}" ]] || return 0
  local line
  line="$(grep -E "^${key}=" "${file}" 2>/dev/null | tail -1 || true)"
  [[ -n "${line}" ]] || return 0
  local value="${line#*=}"
  value="${value%$'\r'}"
  value="${value#\"}"
  value="${value%\"}"
  value="${value#\'}"
  value="${value%\'}"
  printf '%s' "${value}"
}

# Create docker/.env and docker/desktop/.env from examples when missing.
# Docker Desktop opens compose from docker/desktop/ and auto-loads desktop/.env.
ensure_env_files() {
  local source="${ENV_EXAMPLE}"
  if [[ ! -f "${source}" ]]; then
    source="${DESKTOP_ENV_EXAMPLE}"
  fi
  if [[ ! -f "${source}" ]]; then
    echo "Error: missing ${ENV_EXAMPLE} (and ${DESKTOP_ENV_EXAMPLE})" >&2
    exit 1
  fi

  if [[ ! -f "${ENV_FILE}" ]]; then
    cp "${source}" "${ENV_FILE}"
    echo "Created ${ENV_FILE} from template — edit POSTGRES_PASSWORD before sharing this machine."
  fi

  if [[ ! -f "${DESKTOP_ENV_FILE}" ]]; then
    cp "${ENV_FILE}" "${DESKTOP_ENV_FILE}"
    echo "Created ${DESKTOP_ENV_FILE} (Docker Desktop compose auto-loads this path)."
  fi
}

load_postgres_env() {
  ensure_env_files
  local env_source="${ENV_FILE}"

  if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
    POSTGRES_PASSWORD="$(read_env_value POSTGRES_PASSWORD "${env_source}")"
    export POSTGRES_PASSWORD
  fi

  if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
    POSTGRES_PASSWORD="$(read_env_value DB_PASSWORD "${env_source}")"
    export POSTGRES_PASSWORD
  fi

  if [[ -z "${POSTGRES_USER:-}" ]]; then
    POSTGRES_USER="$(read_env_value POSTGRES_USER "${env_source}")"
    POSTGRES_USER="${POSTGRES_USER:-costoptimizer}"
    export POSTGRES_USER
  fi

  if [[ -z "${POSTGRES_DB:-}" ]]; then
    POSTGRES_DB="$(read_env_value POSTGRES_DB "${env_source}")"
    POSTGRES_DB="${POSTGRES_DB:-costoptimizer}"
    export POSTGRES_DB
  fi
}

require_postgres_password() {
  load_postgres_env
  if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
    cat >&2 <<'EOF'
Error: POSTGRES_PASSWORD must be set to a non-empty value in docker/.env.

Setup:
  cp docker/.env.example docker/.env
  # Edit POSTGRES_PASSWORD=changeme (or set DB_PASSWORD as an alias)

PostgreSQL refuses to start without a superuser password.
EOF
    exit 1
  fi
}

upsert_env_var() {
  local key="$1" value="$2" file="$3"
  local tmp
  tmp="$(mktemp)"
  if [[ -f "${file}" ]]; then
    grep -v "^${key}=" "${file}" > "${tmp}" 2>/dev/null || true
  fi
  printf '%s=%s\n' "${key}" "${value}" >> "${tmp}"
  mv "${tmp}" "${file}"
}

enable_microservices_env() {
  ensure_env_files
  for f in "${ENV_FILE}" "${DESKTOP_ENV_FILE}"; do
    upsert_env_var "COMPOSE_PROFILES" "dev" "${f}"
    upsert_env_var "MICROSERVICES_MODE" "1" "${f}"
  done
  echo "Updated ${ENV_FILE} and ${DESKTOP_ENV_FILE}: COMPOSE_PROFILES=dev, MICROSERVICES_MODE=1"
}

print_microservices_urls() {
  echo "Started microservices stack (gateway + 5 platform services + postgres)"
  echo "UI:        http://127.0.0.1:3000"
  echo "Gateway:   http://127.0.0.1:8080"
  echo "Core API:  http://127.0.0.1:8010/health/live"
  echo "Cost API:  http://127.0.0.1:8011/health/live"
  echo "Inventory: http://127.0.0.1:8012/health/live"
  echo "Analysis:  http://127.0.0.1:8013/health/live"
  echo "Metrics:   http://127.0.0.1:8014/health/live"
  echo ""
  echo "Verify: ./build.sh ps"
}

compose() {
  ensure_env_files
  load_postgres_env
  docker compose -p "${COMPOSE_PROJECT_NAME}" -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" "$@"
}

profile_includes_microservices() {
  local profiles
  profiles="$(read_env_value COMPOSE_PROFILES "${ENV_FILE}")"
  [[ "${profiles}" == *microservices* ]]
}
microservices_mode_enabled() {
  local mode
  mode="$(read_env_value MICROSERVICES_MODE "${ENV_FILE}")"
  [[ "${mode}" == "1" || "${mode}" == "true" || "${mode}" == "yes" ]]
}

microservice_containers_exist() {
  docker ps -a --format '{{.Names}}' 2>/dev/null \
    | grep -qE '^costopt-(api-gateway|core-service|cost-service|analysis-service|metrics-service|inventory-service)$'
}

# Compose down only stops services in active profiles; include microservices when the stack was started split.
ensure_compose_profiles_for_down() {
  local profiles
  profiles="$(read_env_value COMPOSE_PROFILES "${ENV_FILE}")"
  if [[ "${profiles}" == *microservices* ]]; then
    export COMPOSE_PROFILES="${profiles}"
    return 0
  fi
  if microservices_mode_enabled || microservice_containers_exist; then
    profiles="${profiles:-dev}"
    export COMPOSE_PROFILES="${profiles},microservices"
    echo "Including microservices profile for compose down (MICROSERVICES_MODE or running microservice containers)."
    return 0
  fi
  export COMPOSE_PROFILES="${profiles}"
}

# Ensure shared python-base exists before building individual platform services.
build_with_profile_deps() {
  local args=("$@")

  if profile_includes_microservices && [[ ${#args[@]} -gt 0 ]]; then
    local arg
    local wants_base=false
    for arg in "${args[@]}"; do
      case "${arg}" in
        python-base) wants_base=false; break ;;
        cost-service|analysis-service|metrics-service|inventory-service|core-service|gateway)
          wants_base=true ;;
      esac
    done
    if [[ "${wants_base}" == true ]]; then
      compose build python-base
    fi
  fi

  compose build "${args[@]}"
}

usage() {
  cat <<'EOF'
Usage: ./docker/build.sh <command>

Commands:
  build       Build images for the active COMPOSE_PROFILES (uses layer cache)
  build-fast  Same as build — explicit cache-friendly alias (BuildKit + COMPOSE_BAKE)
  up          Create/start stack in background (builds only when Dockerfiles changed)
  up-fast     Start stack without rebuilding images (code changes use bind mounts)
  up-microservices  Enable cost/analysis split and start stack (writes docker/.env)
  start       Resume stopped containers (after first up)
  down        Stop and remove containers (keeps volumes)
  logs        Tail service logs (optional service name)
  ps          Show container status
  config      Validate compose file
  reset-db    Stop stack and remove the costopt_pgdata volume
  shell-core    Open a shell in the core-service container
  shell-fe      Open a shell in the frontend container
  shell-cost  Open a shell in the cost-service container (microservices profile)
  shell-analysis Open a shell in the analysis-service container (microservices profile)
  shell-metrics Open a shell in the metrics-service container (microservices profile)
  shell-inventory Open a shell in the inventory-service container (microservices profile)
  help        Show this help

Setup:
  ./docker/build.sh up
  # Auto-creates docker/.env and docker/desktop/.env from .env.example when missing.

Profiles (in docker/.env):
  COMPOSE_PROFILES=dev   — platform microservices + React dev server (default)
  COMPOSE_PROFILES=prod  — nginx frontend + platform microservices + gateway

Quick start:
  ./docker/build.sh up

Fast daily dev (after first build):
  ./docker/build.sh build-fast          # rebuild only when requirements/package.json change
  ./docker/build.sh up-fast             # start without image rebuild
  ./docker/build.sh build core-service   # rebuild one service only

Clean rebuild (slower — invalidates cache):
  ./docker/build.sh build --no-cache
EOF
}

cmd="${1:-help}"
shift || true

case "${cmd}" in
  build|build-fast)
    build_with_profile_deps "$@"
    ;;
  up)
    require_postgres_password
    compose up -d --build "$@"
    echo ""
    print_microservices_urls
    echo "Postgres postgresql://${POSTGRES_USER:-costoptimizer}:<password>@127.0.0.1:5432/${POSTGRES_DB:-costoptimizer}"
    ;;
  up-fast)
    require_postgres_password
    compose up -d "$@"
    echo ""
    print_microservices_urls
    echo "Postgres postgresql://${POSTGRES_USER:-costoptimizer}:<password>@127.0.0.1:5432/${POSTGRES_DB:-costoptimizer}"
    ;;
  up-microservices)
    require_postgres_password
    enable_microservices_env
    compose up -d --build "$@"
    echo ""
    print_microservices_urls
    echo "Postgres postgresql://${POSTGRES_USER:-costoptimizer}:<password>@127.0.0.1:5432/${POSTGRES_DB:-costoptimizer}"
    ;;
  start)
    require_postgres_password
    if ! compose ps -a --format '{{.Name}}' 2>/dev/null | grep -q .; then
      cat >&2 <<EOF
No containers exist for project "${COMPOSE_PROJECT_NAME}".

Docker Desktop "Start" runs docker compose start, which only resumes containers that were created earlier.
Create the stack first:

  cd docker && ./build.sh up

EOF
      exit 1
    fi
    compose start "$@"
  ;;
  down)
    ensure_compose_profiles_for_down
    compose down "$@"
    ;;
  logs)
    compose logs -f "$@"
    ;;
  ps)
    compose ps "$@"
    ;;
  config)
    compose config "$@"
    ;;
  reset-db)
    ensure_compose_profiles_for_down
    compose down
    docker volume rm costopt_pgdata 2>/dev/null || true
    echo "Removed volume costopt_pgdata"
    ;;
  shell-core)
    compose exec core-service sh
    ;;
  shell-fe)
    if compose ps --status running 2>/dev/null | grep -q frontend-dev; then
      compose exec frontend-dev sh
    else
      compose exec frontend-prod sh
    fi
    ;;
  shell-cost)
    compose exec cost-service sh
    ;;
  shell-analysis)
    compose exec analysis-service sh
    ;;
  shell-metrics)
    compose exec metrics-service sh
    ;;
  shell-inventory)
    compose exec inventory-service sh
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "Unknown command: ${cmd}" >&2
    usage >&2
    exit 1
    ;;
esac
