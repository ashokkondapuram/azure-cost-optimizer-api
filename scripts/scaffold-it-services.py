#!/usr/bin/env python3
"""Scaffold IT service folder organization for all Azure resources."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_JSON = ROOT / "packages" / "costoptimizer-core" / "service_registry.json"

# canonical_type -> engine subfolder when name differs
ENGINE_ALIASES: dict[str, str] = {
    "database/cosmosdb": "database/cosmos",
}

# service_id -> extra frontend files still in platform (migrate into it-service over time)
FRONTEND_RELATED: dict[str, list[str]] = {
    "containers-aks": [
        "frontend/src/it-services/containers-aks/utils/aksNormalize.js",
        "frontend/src/pages/AKSClusters.jsx",
    ],
    "network-vnet": ["frontend/src/it-services/network-vnet/utils/vnetNormalize.js"],
    "appservice-webapp": ["frontend/src/it-services/appservice-webapp/utils/appServiceNormalize.js"],
    "network-privateendpoint": ["frontend/src/it-services/network-privateendpoint/utils/privateEndpointNormalize.js"],
    "network-privatedns": ["frontend/src/it-services/network-privatedns/utils/privateDnsNormalize.js"],
    "network-privatelinkservice": ["frontend/src/it-services/network-privatelinkservice/utils/privateLinkServiceNormalize.js"],
    "compute-vm": ["frontend/src/pages/VirtualMachines.jsx"],
    "compute-disk": ["frontend/src/pages/VirtualMachines.jsx"],
}

# service_id -> extra backend modules outside standard paths
BACKEND_EXTRA: dict[str, list[str]] = {
    "compute-disk": [
        "app/disk_utilization.py",
        "app/disk_staleness.py",
        "app/disk_analysis_config.py",
        "app/managed_disk_catalog.py",
    ],
}

DRAWER_UI_SERVICES = frozenset({"compute-disk"})


def service_pkg(service_id: str) -> str:
    return service_id.replace("-", "_")


def resource_module_import(canonical_type: str) -> str:
    category, name = canonical_type.split("/", 1)
    return f"app.resources.{category}.{name}"


def resource_profile_path(canonical_type: str) -> str:
    category, name = canonical_type.split("/", 1)
    return f"app/resources/{category}/{name}.py"


def engine_path(service_id: str) -> str | None:
    pkg = service_pkg(service_id)
    candidate = ROOT / "it_services" / pkg / "engine"
    if candidate.is_dir():
        return str(candidate.relative_to(ROOT)).replace("\\", "/") + "/"
    return None


def arm_match_hint(arm_type: str) -> str:
    # Microsoft.Compute/virtualMachines -> virtualmachines
    tail = arm_type.split("/")[-1] if arm_type else ""
    return tail.lower()


def manifest_yaml(cfg: dict[str, Any], *, drawer_ui: bool) -> str:
    sid = cfg["service_id"]
    pkg = service_pkg(sid)
    canonical = cfg["canonical_type"]
    api_path = f"/resources/{cfg['api_slug']}"
    profile = resource_profile_path(canonical)
    engine = engine_path(sid)
    backend_modules = [f"it_services/{pkg}/resource_profile.py"]
    if sid == "compute-disk":
        backend_modules = [
            "it_services/compute_disk/resource_profile.py",
            "it_services/compute_disk/disk_analysis_config.py",
            "it_services/compute_disk/managed_disk_catalog.py",
            "it_services/compute_disk/data/managed_disk_metrics_thresholds.json",
        ]
    related_app = [profile]
    if engine:
        related_app.append(engine)
    related_app.extend(BACKEND_EXTRA.get(sid, []))
    frontend_related = FRONTEND_RELATED.get(sid, [])
    lines = [
        f"service_id: {sid}",
        f"canonical_type: {canonical}",
        f"display_name: {cfg['display_name']}",
        f"api_path: {api_path}",
        f"arm_type: {cfg.get('arm_type', '')}",
        f"component: {cfg.get('component') or ''}",
        f"drawer_ui: {'true' if drawer_ui else 'false'}",
        "",
        "backend:",
        f"  package: it_services/{pkg}",
        "  modules:",
    ]
    for m in backend_modules:
        lines.append(f"    - {m}")
    lines.append("  related_app_modules:")
    for m in related_app:
        lines.append(f"    - {m}")
    if sid == "compute-disk":
        lines.append("  compatibility_shims:")
        for m in [
            "app/disk_analysis_config.py",
            "app/managed_disk_catalog.py",
            f"app/resources/compute/disk.py",
        ]:
            lines.append(f"    - {m}")
    elif (ROOT / profile).is_file():
        lines.append("  compatibility_shims:")
        lines.append(f"    - {profile}")
    lines.extend([
        "",
        "frontend:",
        f"  root: frontend/src/it-services/{sid}",
        f"  entry: frontend/src/it-services/{sid}/index.js",
    ])
    if frontend_related:
        lines.append("  related_platform_files:")
        for f in frontend_related:
            lines.append(f"    - {f}")
    lines.extend([
        "",
        "platform:",
        "  - frontend/src/it-services/registry.js",
        "",
    ])
    return "\n".join(lines)


def readme_md(cfg: dict[str, Any]) -> str:
    sid = cfg["service_id"]
    return f"""# {cfg['display_name']} (`{sid}`)

IT service folder for **{cfg['canonical_type']}**.

| Layer | Path |
|-------|------|
| Manifest | `it-services/{sid}/manifest.yaml` |
| Backend | `it_services/{service_pkg(sid)}/` |
| Frontend | `frontend/src/it-services/{sid}/` |

Edit only files under this service's backend and frontend folders. See `it-services/README.md`.
"""


def backend_resource_profile(cfg: dict[str, Any]) -> str:
    mod = resource_module_import(cfg["canonical_type"])
    return f'''"""Resource profile — owned by {cfg["service_id"]} IT service."""

from {mod} import (  # noqa: F401
    CANONICAL_TYPE,
    MONITOR_PROFILE,
    TECHNICAL_FETCH_SPEC,
)
'''


def frontend_index(cfg: dict[str, Any]) -> str:
    sid = cfg["service_id"]
    api_path = f"/resources/{cfg['api_slug']}"
    arm_hint = arm_match_hint(cfg.get("arm_type", ""))
    return f'''/**
 * {sid} IT service — frontend public API.
 * See it-services/{sid}/manifest.yaml
 */

import {{ createResourceMatcher }} from '../_shared/createResourceMatcher';

export const SERVICE_ID = '{sid}';
export const API_PATH = '{api_path}';
export const CANONICAL_TYPE = '{cfg["canonical_type"]}';

export const matchesResource = createResourceMatcher({{
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: '{arm_hint}',
}});
'''


def scaffold_service(cfg: dict[str, Any], *, force: bool = False) -> None:
    sid = cfg["service_id"]
    pkg = service_pkg(sid)
    drawer_ui = sid in DRAWER_UI_SERVICES

    it_dir = ROOT / "it-services" / sid
    it_dir.mkdir(parents=True, exist_ok=True)

    manifest_file = it_dir / "manifest.yaml"
    if force or not manifest_file.exists() or sid not in DRAWER_UI_SERVICES:
        manifest_file.write_text(manifest_yaml(cfg, drawer_ui=drawer_ui), encoding="utf-8")

    readme_file = it_dir / "README.md"
    if force or not readme_file.exists():
        readme_file.write_text(readme_md(cfg), encoding="utf-8")

    backend_dir = ROOT / "it_services" / pkg
    backend_dir.mkdir(parents=True, exist_ok=True)
    init_py = backend_dir / "__init__.py"
    if not init_py.exists():
        init_py.write_text("", encoding="utf-8")

    if sid != "compute-disk":
        profile_py = backend_dir / "resource_profile.py"
        if force or not profile_py.exists():
            profile_py.write_text(backend_resource_profile(cfg), encoding="utf-8")

    frontend_dir = ROOT / "frontend" / "src" / "it-services" / sid
    frontend_dir.mkdir(parents=True, exist_ok=True)

    if sid not in DRAWER_UI_SERVICES:
        index_js = frontend_dir / "index.js"
        if force or not index_js.exists():
            index_js.write_text(frontend_index(cfg), encoding="utf-8")
        readme_fe = frontend_dir / "README.md"
        if force or not readme_fe.exists():
            readme_fe.write_text(
                f"Frontend for `{sid}`. See `it-services/{sid}/manifest.yaml`.\n",
                encoding="utf-8",
            )


def write_catalog(services: list[dict[str, Any]]) -> None:
    catalog = {
        "schema_version": 1,
        "description": "IT service file-organization catalog (not runtime microservices)",
        "services": [
            {
                "service_id": s["service_id"],
                "canonical_type": s["canonical_type"],
                "display_name": s["display_name"],
                "api_path": f"/resources/{s['api_slug']}",
                "manifest": f"it-services/{s['service_id']}/manifest.yaml",
                "backend_package": f"it_services/{service_pkg(s['service_id'])}",
                "frontend_root": f"frontend/src/it-services/{s['service_id']}",
                "drawer_ui": s["service_id"] in DRAWER_UI_SERVICES,
            }
            for s in services
        ],
    }
    out = ROOT / "it-services" / "catalog.json"
    out.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")


def write_registry_index(services: list[dict[str, Any]]) -> None:
    enabled = [s["service_id"] for s in services if s["service_id"] in DRAWER_UI_SERVICES]
    out = ROOT / "frontend" / "src" / "it-services" / "registry.enabled.json"
    out.write_text(json.dumps({"drawer_ui_services": enabled}, indent=2) + "\n", encoding="utf-8")


def write_it_services_readme(services: list[dict[str, Any]]) -> None:
    rows = []
    for s in sorted(services, key=lambda x: x["service_id"]):
        sid = s["service_id"]
        drawer = "yes" if sid in DRAWER_UI_SERVICES else "—"
        rows.append(f"| [{s['display_name']}]({sid}/README.md) | `{sid}` | `{s['canonical_type']}` | `/resources/{s['api_slug']}` | {drawer} |")
    table = "\n".join(rows)
    content = f"""# IT services — file organization

Each Azure resource type has a dedicated folder for **backend** and **frontend** code. This is organizational structure only — the app still runs as one deployment.

## Quick start

1. Find your resource in the [catalog](#all-services) below.
2. Open `it-services/<service-id>/manifest.yaml` for owned paths.
3. Edit `it_services/<service_pkg>/` (backend) and `frontend/src/it-services/<service-id>/` (frontend).
4. Enable custom drawer UI in `frontend/src/it-services/registry.js` when ready (`drawer_ui: true` in manifest).

Machine-readable index: [catalog.json](catalog.json)

## Layout

```
it-services/<service-id>/          # Manifest + docs
it_services/<service_pkg>/         # Backend Python
frontend/src/it-services/<id>/   # Frontend React
```

Platform shell (`app/`, `frontend/src/config/`, shared drawer) stays shared.

## All services ({len(services)})

| Display name | Service ID | Canonical type | API path | Drawer UI |
|--------------|------------|----------------|----------|-----------|
{table}

## Scaffold

```bash
python3 scripts/scaffold-it-services.py --all
python3 scripts/scaffold-it-services.py --service compute-vm
```
"""
    (ROOT / "it-services" / "README.md").write_text(content, encoding="utf-8")


def load_services() -> list[dict[str, Any]]:
    return json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold IT service folders for all resources")
    parser.add_argument("--service", help="Scaffold one service id")
    parser.add_argument("--all", action="store_true", help="Scaffold all services from registry")
    parser.add_argument("--force", action="store_true", help="Overwrite generated stubs")
    args = parser.parse_args()

    services = load_services()
    if args.service:
        services = [s for s in services if s["service_id"] == args.service]
        if not services:
            print(f"Unknown service: {args.service}")
            return 1
    elif not args.all:
        parser.error("Specify --all or --service")

    for cfg in services:
        scaffold_service(cfg, force=args.force)
        print(f"Scaffolded {cfg['service_id']}")

    write_catalog(services if args.service else load_services())
    write_registry_index(load_services())
    write_it_services_readme(load_services())
    print(f"Wrote it-services/catalog.json ({len(load_services())} services)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
