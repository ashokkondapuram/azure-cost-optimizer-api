"""Workflow templates linked to optimization rules (owner routing stubs)."""

from __future__ import annotations

from typing import Any

DEFAULT_WORKFLOW_TEMPLATES: dict[str, dict[str, Any]] = {
    "VM_IDLE": {
        "owner_tag": "owner",
        "approval_required": False,
        "sla_days": 7,
        "actions": ["deallocate", "delete"],
    },
    "DISK_UNATTACHED": {
        "owner_tag": "owner",
        "approval_required": True,
        "sla_days": 14,
        "actions": ["snapshot", "delete"],
    },
    "AKS_OVERPROVISIONED": {
        "owner_tag": "platform-owner",
        "approval_required": True,
        "sla_days": 10,
        "actions": ["scale_down", "enable_autoscaler"],
    },
}


def workflow_template_for(rule_id: str) -> dict[str, Any] | None:
    return DEFAULT_WORKFLOW_TEMPLATES.get(rule_id)
