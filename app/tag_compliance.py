"""Tag compliance reporting — surfaces resources missing required tags as findings.

Required tags are configured via the ``tag_compliance`` section of system settings
or the environment variable TAG_REQUIRED_KEYS (comma-separated).

Example finding output::

    {
        "rule_id": "tag_compliance",
        "resource_id": "/subscriptions/.../resourceGroups/rg/providers/.../vm1",
        "resource_name": "vm1",
        "resource_type": "Microsoft.Compute/virtualMachines",
        "severity": "medium",
        "recommendation": "Add missing tags: owner, cost_center",
        "missing_tags": ["owner", "cost_center"],
        "estimated_savings_usd": None,
    }
"""
from __future__ import annotations

import os
from typing import Any

import structlog

log = structlog.get_logger(__name__)

DEFAULT_REQUIRED_TAGS = ["owner", "cost_center", "environment"]


def _load_required_tags(db: Any | None = None) -> list[str]:
    """Load required tag keys from DB settings or environment."""
    if db is not None:
        try:
            from app.services.system_settings import get_effective_config
            cfg = get_effective_config(db, "tag_compliance")
            tags = cfg.get("required_tags") or []
            if isinstance(tags, list) and tags:
                return [t.strip() for t in tags if t.strip()]
            if isinstance(tags, str):
                return [t.strip() for t in tags.split(",") if t.strip()]
        except Exception:
            pass

    env_val = os.getenv("TAG_REQUIRED_KEYS", "").strip()
    if env_val:
        return [t.strip() for t in env_val.split(",") if t.strip()]
    return DEFAULT_REQUIRED_TAGS


def check_resource_tag_compliance(
    resource: dict[str, Any],
    required_tags: list[str],
) -> list[str]:
    """Return list of missing required tag keys for a single resource."""
    tags: dict[str, Any] = resource.get("tags") or {}
    existing = {k.lower() for k in tags}
    return [t for t in required_tags if t.lower() not in existing]


def scan_resources_for_tag_compliance(
    resources: list[dict[str, Any]],
    *,
    db: Any | None = None,
    required_tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Scan a list of ARM resources and return tag-compliance findings.

    Args:
        resources: List of ARM resource dicts (must have ``id``, ``name``, ``type``, ``tags``).
        db: Optional DB session for loading required tags from settings.
        required_tags: Override required tag list (skips DB/env lookup when provided).

    Returns:
        List of finding dicts — one per non-compliant resource.
    """
    tags = required_tags if required_tags is not None else _load_required_tags(db)
    if not tags:
        return []

    findings: list[dict[str, Any]] = []
    for resource in resources:
        missing = check_resource_tag_compliance(resource, tags)
        if not missing:
            continue

        rtype = resource.get("type") or ""
        findings.append({
            "rule_id": "tag_compliance",
            "resource_id": resource.get("id") or "",
            "resource_name": resource.get("name") or "",
            "resource_type": rtype,
            "severity": "medium",
            "recommendation": f"Add missing tags: {', '.join(missing)}",
            "detail": (
                f"Resource '{resource.get('name')}' is missing "
                f"{len(missing)} required tag(s): {', '.join(missing)}."
            ),
            "missing_tags": missing,
            "required_tags": tags,
            "estimated_savings_usd": None,
            "evidence": {
                "existing_tags": list((resource.get("tags") or {}).keys()),
                "missing_tags": missing,
                "required_tags": tags,
            },
        })

    log.info(
        "tag_compliance.scanned",
        total_resources=len(resources),
        non_compliant=len(findings),
        required_tags=tags,
    )
    return findings
