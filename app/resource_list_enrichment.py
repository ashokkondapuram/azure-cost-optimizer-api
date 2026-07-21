"""Post-process resource list API payloads (cost block, disk shape, metrics)."""

from __future__ import annotations

from sqlalchemy.orm import Session


def enrich_resource_list_result(
    result: Any,
    *,
    resource_type: str,
    include_metrics: bool = False,
    db: Session | None = None,
) -> Any:
    """Apply type-specific list enrichment to a list or paginated envelope."""
    canonical = (resource_type or "").strip().lower()
    if canonical != "compute/disk":
        return result

    from app.disk_api_enrichment import enrich_disk_api_rows

    if isinstance(result, list):
        enrich_disk_api_rows(result, include_metrics=include_metrics, db=db)
    elif isinstance(result, dict) and isinstance(result.get("items"), list):
        enrich_disk_api_rows(result["items"], include_metrics=include_metrics, db=db)
    return result
