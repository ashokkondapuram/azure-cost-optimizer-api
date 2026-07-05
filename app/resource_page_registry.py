"""Inventory UI pages — one page per canonical resource type.

Explicit entries cover current nav pages. Generic ARM-sync types in known nav
categories auto-register when a new module is added to ``ALL_RESOURCE_MODULES``.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.resources.registry import TECHNICAL_FETCH_SPECS
from app.resources.types import TechnicalFetchSpec

# Nav categories that expose one inventory page per synced canonical type.
_AUTO_UI_CATEGORY_PREFIXES: frozenset[str] = frozenset({
    "monitoring",
    "integration",
    "messaging",
    "analytics",
    "backup",
    "search",
})


@dataclass(frozen=True)
class ResourcePageDef:
    page_id: str
    canonical_type: str
    api_slug: str
    app_route: str
    title: str
    nav_label: str
    nav_group: str
    dashboard_section: str
    openapi_tag: str


# Pages with custom UI components or non-generic sync stay in appRegistry / main.py.
# These are the per-type pages that replaced aggregate category lists.
_EXPLICIT_PAGES: tuple[ResourcePageDef, ...] = (
    ResourcePageDef(
        page_id="loganalytics",
        canonical_type="monitoring/loganalytics",
        api_slug="loganalytics",
        app_route="/loganalytics",
        title="Log Analytics workspaces",
        nav_label="Log Analytics",
        nav_group="monitoring",
        dashboard_section="platform",
        openapi_tag="Monitoring",
    ),
    ResourcePageDef(
        page_id="appinsights",
        canonical_type="monitoring/appinsights",
        api_slug="appinsights",
        app_route="/appinsights",
        title="Application Insights",
        nav_label="Application Insights",
        nav_group="monitoring",
        dashboard_section="platform",
        openapi_tag="Monitoring",
    ),
    ResourcePageDef(
        page_id="apim",
        canonical_type="integration/apim",
        api_slug="apim",
        app_route="/apim",
        title="API Management",
        nav_label="API Management",
        nav_group="integration",
        dashboard_section="platform",
        openapi_tag="Integration",
    ),
    ResourcePageDef(
        page_id="datafactory",
        canonical_type="integration/datafactory",
        api_slug="datafactory",
        app_route="/datafactory",
        title="Data factories",
        nav_label="Data factories",
        nav_group="integration",
        dashboard_section="platform",
        openapi_tag="Integration",
    ),
    ResourcePageDef(
        page_id="logicapps",
        canonical_type="integration/logicapp",
        api_slug="logicapps",
        app_route="/logicapps",
        title="Logic Apps",
        nav_label="Logic Apps",
        nav_group="integration",
        dashboard_section="platform",
        openapi_tag="Integration",
    ),
    ResourcePageDef(
        page_id="eventhubs",
        canonical_type="messaging/eventhub",
        api_slug="eventhubs",
        app_route="/eventhubs",
        title="Event Hubs",
        nav_label="Event Hubs",
        nav_group="messaging",
        dashboard_section="platform",
        openapi_tag="Messaging",
    ),
    ResourcePageDef(
        page_id="servicebus",
        canonical_type="messaging/servicebus",
        api_slug="servicebus",
        app_route="/servicebus",
        title="Service Bus",
        nav_label="Service Bus",
        nav_group="messaging",
        dashboard_section="platform",
        openapi_tag="Messaging",
    ),
    ResourcePageDef(
        page_id="databricks",
        canonical_type="analytics/databricks",
        api_slug="databricks",
        app_route="/databricks",
        title="Databricks",
        nav_label="Databricks",
        nav_group="analytics",
        dashboard_section="platform",
        openapi_tag="Analytics",
    ),
    ResourcePageDef(
        page_id="synapse",
        canonical_type="analytics/synapse",
        api_slug="synapse",
        app_route="/synapse",
        title="Synapse Analytics",
        nav_label="Synapse Analytics",
        nav_group="analytics",
        dashboard_section="platform",
        openapi_tag="Analytics",
    ),
    ResourcePageDef(
        page_id="adx",
        canonical_type="analytics/adx",
        api_slug="adx",
        app_route="/adx",
        title="Data Explorer",
        nav_label="Data Explorer",
        nav_group="analytics",
        dashboard_section="platform",
        openapi_tag="Analytics",
    ),
    ResourcePageDef(
        page_id="mlworkspace",
        canonical_type="analytics/mlworkspace",
        api_slug="mlworkspace",
        app_route="/mlworkspace",
        title="Machine Learning",
        nav_label="Machine Learning",
        nav_group="analytics",
        dashboard_section="platform",
        openapi_tag="Analytics",
    ),
    ResourcePageDef(
        page_id="recoveryvault",
        canonical_type="backup/recoveryvault",
        api_slug="recoveryvault",
        app_route="/recoveryvault",
        title="Recovery Services vaults",
        nav_label="Recovery vaults",
        nav_group="backup",
        dashboard_section="security",
        openapi_tag="Backup",
    ),
    ResourcePageDef(
        page_id="cognitivesearch",
        canonical_type="search/cognitivesearch",
        api_slug="cognitivesearch",
        app_route="/cognitivesearch",
        title="AI Search",
        nav_label="AI Search",
        nav_group="search",
        dashboard_section="security",
        openapi_tag="Search",
    ),
)

_EXPLICIT_BY_CANONICAL: dict[str, ResourcePageDef] = {
    p.canonical_type: p for p in _EXPLICIT_PAGES
}
_EXPLICIT_BY_ID: dict[str, ResourcePageDef] = {
    p.page_id: p for p in _EXPLICIT_PAGES
}


def _auto_page_from_spec(spec: TechnicalFetchSpec) -> ResourcePageDef | None:
    ct = spec.canonical_type
    if ct in _EXPLICIT_BY_CANONICAL:
        return None
    parts = ct.split("/", 1)
    if len(parts) != 2:
        return None
    prefix, suffix = parts
    if prefix not in _AUTO_UI_CATEGORY_PREFIXES:
        return None
    page_id = suffix.replace("-", "")
    if page_id in _EXPLICIT_BY_ID:
        return None
    title = spec.display_name
    if title and not title.endswith("s"):
        title = f"{title}s"
    tag = prefix.capitalize()
    return ResourcePageDef(
        page_id=page_id,
        canonical_type=ct,
        api_slug=page_id,
        app_route=f"/{page_id}",
        title=title or page_id,
        nav_label=spec.display_name or page_id,
        nav_group=prefix,
        dashboard_section="platform" if prefix != "search" else "security",
        openapi_tag=tag,
    )


def inventory_pages() -> tuple[ResourcePageDef, ...]:
    """All per-type inventory pages, including auto-discovered generic ARM types."""
    pages: dict[str, ResourcePageDef] = dict(_EXPLICIT_BY_ID)
    for spec in TECHNICAL_FETCH_SPECS.values():
        auto = _auto_page_from_spec(spec)
        if auto and auto.page_id not in pages:
            pages[auto.page_id] = auto
    return tuple(sorted(pages.values(), key=lambda p: (p.nav_group, p.title)))


def inventory_page_by_id(page_id: str) -> ResourcePageDef | None:
    for page in inventory_pages():
        if page.page_id == page_id:
            return page
    return None


def api_path_for_page(page: ResourcePageDef) -> str:
    return f"/resources/{page.api_slug}"


# count key == page_id for per-type pages
COUNT_KEY_TO_CANONICAL: dict[str, str] = {
    p.page_id: p.canonical_type for p in inventory_pages()
}

API_PATH_TO_CANONICAL: dict[str, str] = {
    api_path_for_page(p): p.canonical_type for p in inventory_pages()
}

CANONICAL_TO_APP_ROUTE: dict[str, str] = {
    p.canonical_type: p.app_route for p in inventory_pages()
}

CANONICAL_TO_COUNT_KEY: dict[str, str] = {
    p.canonical_type: p.page_id for p in inventory_pages()
}


def count_key_for_canonical(canonical_type: str) -> str | None:
    return CANONICAL_TO_COUNT_KEY.get((canonical_type or "").strip().lower())


def app_route_for_canonical(canonical_type: str) -> str | None:
    return CANONICAL_TO_APP_ROUTE.get((canonical_type or "").strip().lower())


def pages_catalog() -> list[dict]:
    return [
        {
            "page_id": p.page_id,
            "canonical_type": p.canonical_type,
            "api_path": api_path_for_page(p),
            "app_route": p.app_route,
            "title": p.title,
            "nav_label": p.nav_label,
            "nav_group": p.nav_group,
            "dashboard_section": p.dashboard_section,
            "count_key": p.page_id,
        }
        for p in inventory_pages()
    ]
