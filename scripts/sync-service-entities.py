#!/usr/bin/env python3
"""Generate per-resource service.py entity files under it_services/<package>/."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "packages" / "costoptimizer-core" / "service_registry.json"
ENGINE_CATALOG = ROOT / "it_services" / "_engine_catalog.json"


def _package(service_id: str) -> str:
    return service_id.replace("-", "_")


def _engine_meta() -> dict[str, dict]:
    if not ENGINE_CATALOG.is_file():
        return {}
    rows = json.loads(ENGINE_CATALOG.read_text(encoding="utf-8"))
    return {row["service_id"]: row for row in rows}


def _render(row: dict, engine: dict | None) -> str:
    service_id = row["service_id"]
    package = _package(service_id)
    class_name = (engine or {}).get("class_name")
    engine_import = ""
    sub_engine_export = "SubEngine = None  # profile-only service"
    if class_name:
        engine_import = f"from it_services.{package}.engine.sub_engine import {class_name} as SubEngine"
        sub_engine_export = ""

    return textwrap.dedent(
        f'''\
        """IT service entity — public exports for {row.get("display_name") or service_id}."""

        from __future__ import annotations

        SERVICE_ID = "{service_id}"
        CANONICAL_TYPE = "{row.get("canonical_type", "")}"
        ARM_TYPE = "{row.get("arm_type", "")}"
        DISPLAY_NAME = "{row.get("display_name", "")}"
        API_SLUG = "{row.get("api_slug", "")}"
        COMPONENT = "{row.get("component", "")}"

        from it_services.{package}.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

        {engine_import}
        {sub_engine_export}
        '''
    ).lstrip()


def main() -> int:
    rows = json.loads(REGISTRY.read_text(encoding="utf-8"))
    engines = _engine_meta()
    written = 0
    for row in rows:
        package = _package(row["service_id"])
        target = ROOT / "it_services" / package / "service.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        content = _render(row, engines.get(row["service_id"]))
        if target.exists() and target.read_text(encoding="utf-8") == content:
            continue
        target.write_text(content, encoding="utf-8")
        written += 1

        init_path = target.parent / "__init__.py"
        init_body = f'"""{row.get("display_name") or row["service_id"]} IT service package."""\n'
        if not init_path.exists() or init_path.read_text(encoding="utf-8") != init_body:
            init_path.write_text(init_body, encoding="utf-8")
            written += 1

    print(f"sync-service-entities: wrote or updated {written} service.py files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
