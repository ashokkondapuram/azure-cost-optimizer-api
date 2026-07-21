"""Managed disk analysis configuration — disk-assessment.json is authoritative."""

from __future__ import annotations

from typing import Any

from it_services.compute_disk.assessment_bridge import (
    disk_rule_ids,
    extended_disk_spec_payload,
    hydrate_disk_rules,
)

__all__ = [
    "disk_rule_ids",
    "extended_disk_spec_payload",
    "hydrate_disk_rules",
    "supplemental_disk_rules",
]


def supplemental_disk_rules() -> dict[str, Any]:
    """Disk rules are defined in disk-assessment.json and hydrated onto ADVANCED_RULES."""
    return {}
