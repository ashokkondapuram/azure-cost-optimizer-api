# Docker Desktop shortcuts — run from repository root
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
REPO := $(abspath $(ROOT)/..)
COMPOSE := docker compose -f $(ROOT)/desktop/docker-compose.yml --env-file $(if $(wildcard $(ROOT)/.env),$(ROOT)/.env,$(ROOT)/.env.example)

.PHONY: help docker-build docker-build-fast docker-up docker-up-fast docker-down docker-logs docker-ps docker-config docker-reset-db

help:
	@echo "Docker Desktop targets (see docker/README.md):"
	@echo "  make docker-build"
	@echo "  make docker-build-fast"
	@echo "  make docker-up"
	@echo "  make docker-up-fast"
	@echo "  make docker-down"
	@echo "  make docker-logs"
	@echo "  make docker-ps"
	@echo "  make docker-config"
	@echo "  make docker-reset-db"

docker-build:
	DOCKER_BUILDKIT=1 COMPOSE_BAKE=true $(COMPOSE) build

docker-build-fast: docker-build

docker-up:
	@test -f $(ROOT)/.env || cp $(ROOT)/.env.example $(ROOT)/.env
	@test -f $(ROOT)/desktop/.env || cp $(ROOT)/.env $(ROOT)/desktop/.env
	DOCKER_BUILDKIT=1 COMPOSE_BAKE=true $(COMPOSE) up -d --build

docker-up-fast:
	@test -f $(ROOT)/.env || cp $(ROOT)/.env.example $(ROOT)/.env
	@test -f $(ROOT)/desktop/.env || cp $(ROOT)/.env $(ROOT)/desktop/.env
	$(COMPOSE) up -d

docker-down:
	$(COMPOSE) down

docker-logs:
	$(COMPOSE) logs -f

docker-ps:
	$(COMPOSE) ps

docker-config:
	$(COMPOSE) config

docker-reset-db:
	$(COMPOSE) down
	-docker volume rm costopt_pgdata
