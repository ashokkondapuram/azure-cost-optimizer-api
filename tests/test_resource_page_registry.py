"""Tests for per-type inventory page registry."""

from app.resource_page_registry import (
    API_PATH_TO_CANONICAL,
    COUNT_KEY_TO_CANONICAL,
    inventory_pages,
)


def test_inventory_pages_include_split_monitoring_types():
    types = {p.canonical_type for p in inventory_pages()}
    assert "monitoring/loganalytics" in types
    assert "monitoring/appinsights" in types


def test_loganalytics_api_path_maps_to_canonical_type():
    assert API_PATH_TO_CANONICAL["/resources/loganalytics"] == "monitoring/loganalytics"
    assert COUNT_KEY_TO_CANONICAL["loganalytics"] == "monitoring/loganalytics"


def test_all_inventory_pages_have_unique_ids_and_paths():
    pages = inventory_pages()
    assert len({p.page_id for p in pages}) == len(pages)
    assert len({p.app_route for p in pages}) == len(pages)
    assert len({p.api_slug for p in pages}) == len(pages)
