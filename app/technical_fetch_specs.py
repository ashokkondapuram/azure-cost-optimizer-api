"""Backward-compatible shim — use app.resources instead."""

from app.resources import (
    TECHNICAL_FETCH_SPECS,
    TechnicalFetchSpec,
    TechnicalFieldDef,
    UsageMetricDef,
    extract_technical_facts,
    generic_arm_sync_types,
    get_technical_fetch_spec,
    get_technical_fetch_spec_by_arm,
    list_technical_fetch_specs,
    pick_sync_properties,
    sku_text,
)

_sku_text = sku_text

__all__ = [
    "TECHNICAL_FETCH_SPECS",
    "TechnicalFetchSpec",
    "TechnicalFieldDef",
    "UsageMetricDef",
    "_sku_text",
    "extract_technical_facts",
    "generic_arm_sync_types",
    "get_technical_fetch_spec",
    "get_technical_fetch_spec_by_arm",
    "list_technical_fetch_specs",
    "pick_sync_properties",
]
