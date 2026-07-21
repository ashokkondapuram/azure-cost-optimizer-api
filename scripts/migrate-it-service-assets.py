#!/usr/bin/env python3
"""Migrate resource profiles and network optimization_rules into IT service folders."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_JSON = ROOT / "packages" / "costoptimizer-core" / "service_registry.json"

NETWORK_RULES: dict[str, str] = {
    "vnet": "network_vnet",
    "privateendpoint": "network_privateendpoint",
    "privatelinkservice": "network_privatelinkservice",
    "privatedns": "network_privatedns",
}

NETWORK_ANALYSIS_IMPORTS: dict[str, str] = {
    "app.optimizer.resource_engines.network.privateendpoint.optimization_rules": (
        "it_services.network_privateendpoint.engine.optimization_rules"
    ),
    "app.optimizer.resource_engines.network.privatelinkservice.optimization_rules": (
        "it_services.network_privatelinkservice.engine.optimization_rules"
    ),
    "app.optimizer.resource_engines.network.privatedns.optimization_rules": (
        "it_services.network_privatedns.engine.optimization_rules"
    ),
    "app.optimizer.resource_engines.network.vnet.optimization_rules": (
        "it_services.network_vnet.engine.optimization_rules"
    ),
}


def service_pkg(service_id: str) -> str:
    return service_id.replace("-", "_")


def write_shim(target: Path, import_path: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f'"""Compatibility shim — implementation: {import_path}"""\n\n'
        "from importlib import import_module\n\n"
        f'_impl = import_module("{import_path}")\n\n\n'
        "def __getattr__(name: str):\n"
        "    return getattr(_impl, name)\n",
        encoding="utf-8",
    )


def resource_src(canonical_type: str) -> Path:
    category, name = canonical_type.split("/", 1)
    return ROOT / "app" / "resources" / category / f"{name}.py"


def migrate_resource_profiles() -> int:
    services = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
    count = 0
    for cfg in services:
        sid = cfg["service_id"]
        pkg = service_pkg(sid)
        canonical = cfg["canonical_type"]
        src = resource_src(canonical)
        if not src.is_file():
            print(f"skip profile (no source): {src}")
            continue
        text = src.read_text(encoding="utf-8")
        if 'Compatibility shim' in text.splitlines()[0] if text else '':
            continue
        dst = ROOT / "it_services" / pkg / "resource_profile.py"
        header = f'"""Resource profile — owned by {sid} IT service."""\n\n'
        body = text
        if not body.lstrip().startswith('"""Resource profile'):
            body = re.sub(r'^"""[^"]*"""\n+', "", body, count=1)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(header + body.lstrip(), encoding="utf-8")
        write_shim(src, f"it_services.{pkg}.resource_profile")
        count += 1

    # SQL database monitor profile (child of SQL server — same IT service)
    sql_db_src = ROOT / "app" / "resources" / "database" / "sql_database.py"
    if sql_db_src.is_file() and "Compatibility shim" not in sql_db_src.read_text(encoding="utf-8")[:80]:
        dst = ROOT / "it_services" / "database_sql" / "sql_database_profile.py"
        text = sql_db_src.read_text(encoding="utf-8")
        dst.write_text(
            '"""SQL database monitor profile — owned by database-sql IT service."""\n\n'
            + re.sub(r'^"""[^"]*"""\n+', "", text, count=1).lstrip(),
            encoding="utf-8",
        )
        write_shim(sql_db_src, "it_services.database_sql.sql_database_profile")
        count += 1

    return count


def migrate_network_optimization_rules() -> int:
    count = 0
    for engine_name, pkg in NETWORK_RULES.items():
        src = (
            ROOT
            / "app"
            / "optimizer"
            / "resource_engines"
            / "network"
            / engine_name
            / "optimization_rules.py"
        )
        if not src.is_file():
            continue
        text = src.read_text(encoding="utf-8")
        if "Compatibility shim" in text[:120]:
            continue
        dst = ROOT / "it_services" / pkg / "engine" / "optimization_rules.py"
        dst.parent.mkdir(parents=True, exist_ok=True)
        header = f'"""Optimization rules — owned by {pkg.replace("_", "-")} IT service."""\n\n'
        body = re.sub(r'^"""[^"]*"""\n+', "", text, count=1).lstrip()
        dst.write_text(header + body, encoding="utf-8")
        write_shim(src, f"it_services.{pkg}.engine.optimization_rules")
        count += 1
    return count


def update_network_analysis_imports() -> int:
    count = 0
    for path in (ROOT / "it_services").glob("network_*/engine/analysis.py"):
        text = path.read_text(encoding="utf-8")
        updated = text
        for old, new in NETWORK_ANALYSIS_IMPORTS.items():
            updated = updated.replace(old, new)
        if updated != text:
            path.write_text(updated, encoding="utf-8")
            count += 1
    return count


def main() -> None:
    profiles = migrate_resource_profiles()
    rules = migrate_network_optimization_rules()
    analysis = update_network_analysis_imports()
    print(
        f"Migration complete: {profiles} resource profiles, "
        f"{rules} network optimization_rules, {analysis} analysis imports updated."
    )


if __name__ == "__main__":
    main()
