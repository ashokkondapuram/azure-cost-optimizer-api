"""Data access helpers for unified persistence tables."""

from app.data_store.enrichment_registry import (
    all_enrichment_table_names,
    enrichment_table_name,
    ensure_all_enrichment_tables,
    get_enrichment_model,
    has_enrichment_table,
    iter_enrichment_models,
    registered_enrichment_types,
    resolve_canonical_type,
)

__all__ = [
    "all_enrichment_table_names",
    "enrichment_table_name",
    "ensure_all_enrichment_tables",
    "get_enrichment_model",
    "has_enrichment_table",
    "iter_enrichment_models",
    "registered_enrichment_types",
    "resolve_canonical_type",
]
