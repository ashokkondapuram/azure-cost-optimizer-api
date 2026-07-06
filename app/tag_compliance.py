"""Tag Compliance — audit how consistently Azure resources are tagged.

Scans the synced ``resources`` table and checks each resource's ``tags``
JSON column against a configurable list of required tag keys.  Returns
per-resource-type coverage metrics plus a list of non-compliant resources.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# Default required tag keys — override via the ``required_tags`` parameter.
_DEFAULT_REQUIRED_TAGS = ["Environment", "Owner", "CostCenter"]


def get_tag_compliance(
    db: Session,
    subscription_id: str | None = None,
    required_tags: list[str] | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Return tag compliance statistics and a page of non-compliant resources."""
    required = [t.strip() for t in (required_tags or _DEFAULT_REQUIRED_TAGS) if t.strip()]
    sub_clause = "AND subscription_id = :sub" if subscription_id else ""

    sql = text(
        f"""
        SELECT
            arm_resource_id,
            name,
            resource_type,
            resource_group,
            tags
        FROM resources
        WHERE 1 = 1
        {sub_clause}
        ORDER BY resource_type, name
        """
    )
    params: dict[str, Any] = {}
    if subscription_id:
        params["sub"] = subscription_id

    try:
        rows = db.execute(sql, params).fetchall()
    except Exception:
        rows = []

    total = len(rows)
    compliant = 0
    non_compliant_rows: list[dict] = []
    type_stats: dict[str, dict] = {}

    import json

    for row in rows:
        rid, name, rtype, rg, tags_raw = row[0], row[1], row[2], row[3], row[4]
        try:
            tags: dict[str, str] = json.loads(tags_raw) if isinstance(tags_raw, str) else (tags_raw or {})
        except Exception:
            tags = {}

        tag_keys_lower = {k.lower() for k in tags}
        missing = [t for t in required if t.lower() not in tag_keys_lower]
        is_compliant = len(missing) == 0

        if is_compliant:
            compliant += 1

        # Per-type stats.
        rtype_key = rtype or "(unknown)"
        if rtype_key not in type_stats:
            type_stats[rtype_key] = {"total": 0, "compliant": 0}
        type_stats[rtype_key]["total"] += 1
        if is_compliant:
            type_stats[rtype_key]["compliant"] += 1

        if not is_compliant:
            non_compliant_rows.append(
                {
                    "resource_id": rid,
                    "name": name,
                    "resource_type": rtype,
                    "resource_group": rg,
                    "missing_tags": missing,
                    "present_tags": list(tags.keys()),
                }
            )

    # Pagination of non-compliant list.
    offset = (page - 1) * page_size
    page_items = non_compliant_rows[offset : offset + page_size]

    # Build type summary.
    type_summary = [
        {
            "resource_type": t,
            "total": v["total"],
            "compliant": v["compliant"],
            "non_compliant": v["total"] - v["compliant"],
            "coverage_pct": round(100 * v["compliant"] / v["total"], 1) if v["total"] else 0.0,
        }
        for t, v in sorted(type_stats.items(), key=lambda x: x[1]["total"] - x[1]["compliant"], reverse=True)
    ]

    return {
        "subscription_id": subscription_id,
        "required_tags": required,
        "summary": {
            "total_resources": total,
            "compliant": compliant,
            "non_compliant": total - compliant,
            "coverage_pct": round(100 * compliant / total, 1) if total else 0.0,
        },
        "by_type": type_summary,
        "non_compliant_resources": page_items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_non_compliant": len(non_compliant_rows),
        },
    }
