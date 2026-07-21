"""Service registry — maps canonical resource types to microservice metadata."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

# Pilot + fully wired services (gateway routes here first).
MIGRATED_SERVICES: frozenset[str] = frozenset({
    "compute-disk",
    "security-keyvault",
})

RESOURCE_PORT_BASE = int(os.getenv("RESOURCE_SERVICE_PORT_BASE", "8101"))


@dataclass(frozen=True)
class ServiceConfig:
    service_id: str
    canonical_type: str
    api_slug: str
    component: str | None
    arm_type: str | None
    display_name: str | None
    port: int
    migrated: bool = False

    @property
    def base_url(self) -> str:
        host = os.getenv(f"SERVICE_HOST_{self.service_id.upper().replace('-', '_')}", self.service_id)
        return os.getenv(
            f"SERVICE_URL_{self.service_id.upper().replace('-', '_')}",
            f"http://{host}:{self.port}",
        )

    @property
    def gateway_path(self) -> str:
        return f"/api/resources/{self.api_slug}"


def service_id_for_canonical(canonical_type: str) -> str:
    category, name = canonical_type.split("/", 1)
    return f"{category}-{name.replace('_', '-')}"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_registry_from_app() -> list[ServiceConfig]:
    """Build registry from monolith modules (requires repo root on sys.path)."""
    import sys

    root = str(_repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)

    from app.optimizer.component_map import CANONICAL_TO_COMPONENT
    from app.resource_page_registry import inventory_pages
    from app.resources.registry import TECHNICAL_FETCH_SPECS
    from app.sync_scope import API_PATH_TO_TYPE

    slug_by_canonical: dict[str, str] = {}
    for path, ct in API_PATH_TO_TYPE.items():
        if path.startswith("/resources/"):
            slug_by_canonical[ct] = path.removeprefix("/resources/").strip("/")
    for page in inventory_pages():
        slug_by_canonical.setdefault(page.canonical_type, page.api_slug)

    configs: list[ServiceConfig] = []
    port = RESOURCE_PORT_BASE
    for canonical_type in sorted(TECHNICAL_FETCH_SPECS.keys()):
        spec = TECHNICAL_FETCH_SPECS[canonical_type]
        service_id = service_id_for_canonical(canonical_type)
        api_slug = slug_by_canonical.get(canonical_type, service_id.split("-", 1)[-1])
        configs.append(
            ServiceConfig(
                service_id=service_id,
                canonical_type=canonical_type,
                api_slug=api_slug,
                component=CANONICAL_TO_COMPONENT.get(canonical_type),
                arm_type=spec.arm_type,
                display_name=spec.display_name,
                port=port,
                migrated=service_id in MIGRATED_SERVICES,
            )
        )
        port += 1
    return configs


@lru_cache(maxsize=1)
def all_service_configs() -> tuple[ServiceConfig, ...]:
    cache_file = _repo_root() / "packages" / "costoptimizer-core" / "service_registry.json"
    if cache_file.is_file():
        try:
            raw = json.loads(cache_file.read_text(encoding="utf-8"))
            return tuple(
                ServiceConfig(
                    migrated=row.get("migrated", row["service_id"] in MIGRATED_SERVICES),
                    **{k: v for k, v in row.items() if k != "migrated"},
                )
                for row in raw
            )
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    return tuple(_load_registry_from_app())


def get_service_config(service_id: str) -> ServiceConfig:
    for cfg in all_service_configs():
        if cfg.service_id == service_id:
            return cfg
    raise KeyError(f"Unknown service: {service_id}")


def get_service_by_api_slug(api_slug: str) -> ServiceConfig | None:
    slug = (api_slug or "").strip().strip("/")
    for cfg in all_service_configs():
        if cfg.api_slug == slug:
            return cfg
    return None


def get_service_by_canonical(canonical_type: str) -> ServiceConfig | None:
    key = (canonical_type or "").strip().lower()
    for cfg in all_service_configs():
        if cfg.canonical_type == key:
            return cfg
    return None


def registry_as_json() -> list[dict[str, Any]]:
    return [
        {
            "service_id": c.service_id,
            "canonical_type": c.canonical_type,
            "api_slug": c.api_slug,
            "component": c.component,
            "arm_type": c.arm_type,
            "display_name": c.display_name,
            "port": c.port,
            "migrated": c.migrated,
        }
        for c in all_service_configs()
    ]
