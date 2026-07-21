"""OpenAPI schema for the in-app explorer — Azure ARM URLs plus app Cost Management APIs."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.azure_arm_openapi import build_azure_arm_openapi_schema

_COST_TAG = "Cost Management"


def merge_cost_management_paths(
    arm_schema: dict[str, Any],
    native_schema: dict[str, Any],
) -> dict[str, Any]:
    """Add /api/costs/* operations from FastAPI routes to the explorer OpenAPI document."""
    merged_paths = dict(arm_schema.get("paths") or {})
    for path, path_item in (native_schema.get("paths") or {}).items():
        if not path.startswith("/costs"):
            continue
        merged_paths[f"/api{path}"] = path_item

    tags = list(arm_schema.get("tags") or [])
    tag_names = {t.get("name") for t in tags}
    native_tags = {t.get("name"): t for t in native_schema.get("tags") or []}
    if _COST_TAG in native_tags and _COST_TAG not in tag_names:
        tags.append(native_tags[_COST_TAG])
    elif _COST_TAG not in tag_names:
        tags.append({
            "name": _COST_TAG,
            "description": "Synced Azure costs, Cost Explorer bundle, and manual sync.",
        })

    components = dict(arm_schema.get("components") or {})
    native_components = native_schema.get("components") or {}
    for section in ("schemas", "parameters", "responses"):
        if section not in native_components:
            continue
        section_merge = dict(components.get(section) or {})
        section_merge.update(native_components[section])
        components[section] = section_merge

    info = dict(arm_schema.get("info") or {})
    description = str(info.get("description") or "")
    if _COST_TAG not in description:
        info["description"] = (
            f"{description.rstrip()} "
            "Cost Management endpoints under /api/costs call this app directly "
            "(database-backed; set prefer_live=true for on-demand Azure fetch)."
        ).strip()

    return {
        **arm_schema,
        "info": info,
        "tags": tags,
        "paths": merged_paths,
        "components": components,
    }


def configure_openapi(app: FastAPI) -> None:
    """Register OpenAPI generator: Azure ARM proxy paths + app Cost Management APIs."""

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        arm_schema = build_azure_arm_openapi_schema(version=app.version)
        native_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        app.openapi_schema = merge_cost_management_paths(arm_schema, native_schema)
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
