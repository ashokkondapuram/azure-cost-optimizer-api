#!/usr/bin/env python3
"""Generate per-resource microservice folders from the shared resource registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "costoptimizer-core"))

from costoptimizer_core.registry import (  # noqa: E402
    MIGRATED_SERVICES,
    registry_as_json,
    service_id_for_canonical,
    _load_registry_from_app,
)


SERVICE_MAIN_TEMPLATE = '''"""Microservice for {canonical_type} ({display_name})."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[{root_depth}]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from costoptimizer_core import create_resource_service, get_service_config

SERVICE_ID = "{service_id}"
app = create_resource_service(get_service_config(SERVICE_ID))

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "{port}"))
    uvicorn.run(
        "service_app:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=port,
        reload=os.getenv("RELOAD", "") == "1",
    )
'''

DOCKERFILE_TEMPLATE = '''FROM python:3.13-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY packages/costoptimizer-core /app/packages/costoptimizer-core
RUN pip install --no-cache-dir -e /app/packages/costoptimizer-core

COPY app /app/app
COPY data /app/data
COPY services/resources/{service_id}/src /app/services/resources/{service_id}/src

ENV PORT={port}
WORKDIR /app/services/resources/{service_id}/src
CMD ["uvicorn", "service_app:app", "--host", "127.0.0.1", "--port", "{port}"]
'''

COMPUTE_DISK_DOCKERFILE_TEMPLATE = '''FROM python:3.13-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY packages/costoptimizer-core /app/packages/costoptimizer-core
RUN pip install --no-cache-dir -e /app/packages/costoptimizer-core

COPY app /app/app
COPY data /app/data
COPY it_services /app/it_services
COPY services/resources/compute-disk/src /app/services/resources/compute-disk/src

ENV PORT={port}
ENV ASSESSMENT_DATA_DIR=/app/data
WORKDIR /app/services/resources/compute-disk/src
CMD ["uvicorn", "service_app:app", "--host", "127.0.0.1", "--port", "{port}"]
'''

PYPROJECT_TEMPLATE = '''[project]
name = "{service_id}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = []

[tool.setuptools]
py-modules = []
'''

UI_README_TEMPLATE = '''# {service_id}

IT service file organization — see `it-services/README.md`.

- Backend: `it_services/{service_pkg}/`
- Frontend: `frontend/src/it-services/{service_id}/`
- Manifest: `it-services/{service_id}/manifest.yaml`
- Register UI in `frontend/src/it-services/registry.js`

See `it-services/compute-disk/` for the managed disks pilot.
'''

UI_INDEX_TEMPLATE = '''/**
 * {service_id} IT service — frontend public API.
 */

export const SERVICE_ID = '{service_id}';
export const API_PATH = '/resources/{api_slug}';
export const CANONICAL_TYPE = '{canonical_type}';

export function matchesResource(_resource, _apiPath = '') {{
  return false;
}}
'''

IT_MANIFEST_TEMPLATE = '''service_id: {service_id}
canonical_type: {canonical_type}
display_name: {display_name}
api_path: /resources/{api_slug}

backend:
  package: it_services/{service_pkg}
  modules: []

frontend:
  root: frontend/src/it-services/{service_id}
  entry: frontend/src/it-services/{service_id}/index.js

platform:
  - frontend/src/it-services/registry.js
'''

TEST_TEMPLATE = '''"""Contract tests for {service_id} microservice."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages" / "costoptimizer-core"))


@pytest.fixture
def client():
    import importlib.util

    service_src = ROOT / "services" / "resources" / "{service_id}" / "src" / "service_app.py"
    spec = importlib.util.spec_from_file_location("{service_id}_service_app", service_src)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return TestClient(module.app)


def test_health_live(client):
    res = client.get("/health/live")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service_id"] == "{service_id}"


def test_meta(client):
    res = client.get("/v1/meta")
    assert res.status_code == 200
    body = res.json()
    assert body["canonical_type"] == "{canonical_type}"
    assert body["api_slug"] == "{api_slug}"
'''


def write_service(cfg, *, force: bool = False) -> Path:
    service_dir = ROOT / "services" / "resources" / cfg.service_id
    src_dir = service_dir / "src"
    tests_dir = service_dir / "tests"
    src_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)

    main_py = src_dir / "service_app.py"
    if force or not main_py.exists():
        main_py.write_text(
            SERVICE_MAIN_TEMPLATE.format(
                canonical_type=cfg.canonical_type,
                display_name=cfg.display_name or cfg.service_id,
                service_id=cfg.service_id,
                port=cfg.port,
                root_depth=4,
            ),
            encoding="utf-8",
        )
    legacy_main = src_dir / "main.py"
    if legacy_main.exists():
        legacy_main.unlink()

    dockerfile = service_dir / "Dockerfile"
    if force or not dockerfile.exists():
        template = COMPUTE_DISK_DOCKERFILE_TEMPLATE if cfg.service_id == "compute-disk" else DOCKERFILE_TEMPLATE
        dockerfile.write_text(template.format(service_id=cfg.service_id, port=cfg.port), encoding="utf-8")

    pyproject = service_dir / "pyproject.toml"
    if force or not pyproject.exists():
        pyproject.write_text(PYPROJECT_TEMPLATE.format(service_id=cfg.service_id), encoding="utf-8")

    test_file = tests_dir / f"test_{cfg.service_id.replace('-', '_')}_contract.py"
    if force or not test_file.exists():
        test_file.write_text(
            TEST_TEMPLATE.format(
                service_id=cfg.service_id,
                canonical_type=cfg.canonical_type,
                api_slug=cfg.api_slug,
            ),
            encoding="utf-8",
        )

    return service_dir


def write_service_ui(cfg, *, force: bool = False) -> Path | None:
    if cfg.service_id == "compute-disk":
        return None

    service_pkg = cfg.service_id.replace("-", "_")
    it_service_dir = ROOT / "it-services" / cfg.service_id
    it_service_dir.mkdir(parents=True, exist_ok=True)

    manifest = it_service_dir / "manifest.yaml"
    if force or not manifest.exists():
        manifest.write_text(
            IT_MANIFEST_TEMPLATE.format(
                service_id=cfg.service_id,
                api_slug=cfg.api_slug,
                canonical_type=cfg.canonical_type,
                display_name=cfg.display_name or cfg.service_id,
                service_pkg=service_pkg,
            ),
            encoding="utf-8",
        )

    readme = it_service_dir / "README.md"
    if force or not readme.exists():
        readme.write_text(
            UI_README_TEMPLATE.format(service_id=cfg.service_id),
            encoding="utf-8",
        )

    frontend_dir = ROOT / "frontend" / "src" / "it-services" / cfg.service_id
    frontend_dir.mkdir(parents=True, exist_ok=True)

    index_js = frontend_dir / "index.js"
    if force or not index_js.exists():
        index_js.write_text(
            UI_INDEX_TEMPLATE.format(
                service_id=cfg.service_id,
                api_slug=cfg.api_slug,
                canonical_type=cfg.canonical_type,
            ),
            encoding="utf-8",
        )

    backend_pkg = ROOT / "it_services" / service_pkg
    backend_pkg.mkdir(parents=True, exist_ok=True)
    init_py = backend_pkg / "__init__.py"
    if force or not init_py.exists():
        init_py.write_text("", encoding="utf-8")

    return it_service_dir


def write_registry_json() -> Path:
    out = ROOT / "packages" / "costoptimizer-core" / "service_registry.json"
    configs = _load_registry_from_app()
    rows = []
    for cfg in configs:
        rows.append({
            "service_id": cfg.service_id,
            "canonical_type": cfg.canonical_type,
            "api_slug": cfg.api_slug,
            "component": cfg.component,
            "arm_type": cfg.arm_type,
            "display_name": cfg.display_name,
            "port": cfg.port,
            "migrated": cfg.service_id in MIGRATED_SERVICES,
        })
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return out


def write_compose_snippet(configs) -> Path:
  out = ROOT / "services" / "resources" / "docker-compose.services.generated.yml"
  out.parent.mkdir(parents=True, exist_ok=True)
  lines = ["# Auto-generated — do not edit manually", "services:"]
  for cfg in configs:
      env_name = cfg.service_id.upper().replace("-", "_")
      lines.extend([
          f"  {cfg.service_id}:",
          f"    build:",
          f"      context: ../..",
          f"      dockerfile: services/resources/{cfg.service_id}/Dockerfile",
          f"    environment:",
          f"      - PORT={cfg.port}",
          f"      - DATABASE_URL=${{DATABASE_URL}}",
          f"      - SERVICE_URL_{env_name}=http://{cfg.service_id}:{cfg.port}",
          f"    ports:",
          f'      - "127.0.0.1:{cfg.port}:{cfg.port}"',
          f"    depends_on:",
          f"      - postgres",
          "",
      ])
  out.write_text("\n".join(lines), encoding="utf-8")
  return out


def write_gateway_routes(configs) -> Path:
    out = ROOT / "services" / "platform-gateway" / "routes.generated.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    routes = []
    for cfg in configs:
        routes.append({
            "path_prefix": f"/api/resources/{cfg.api_slug}",
            "target": f"http://{cfg.service_id}:{cfg.port}" if cfg.migrated else "${INVENTORY_SERVICE_URL}",
            "migrated": cfg.migrated,
            "service_id": cfg.service_id,
        })
    import yaml

    out.write_text(yaml.dump({"routes": routes}, sort_keys=False), encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold per-resource microservices")
    parser.add_argument("--service", help="Scaffold one service id (e.g. compute-disk)")
    parser.add_argument("--all", action="store_true", help="Scaffold all resource services")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument("--registry-only", action="store_true", help="Only regenerate service_registry.json")
    args = parser.parse_args()

    configs = _load_registry_from_app()
    registry_path = write_registry_json()
    print(f"Wrote {registry_path} ({len(configs)} services)")

    if args.registry_only:
        return 0

    write_compose_snippet(configs)
    write_gateway_routes(configs)

    targets = configs
    if args.service:
        targets = [c for c in configs if c.service_id == args.service]
        if not targets:
            print(f"Unknown service: {args.service}", file=sys.stderr)
            return 1

    if not args.all and not args.service:
        parser.error("Specify --all or --service")

    for cfg in targets:
        path = write_service(cfg, force=args.force)
        print(f"Scaffolded {path}")
        print(f"  → run: python3 scripts/scaffold-it-services.py --service {cfg.service_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
