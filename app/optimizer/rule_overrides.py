"""Apply persisted / request-time overrides onto rule dataclass instances."""
from __future__ import annotations

from enum import Enum
from typing import Any


SEVERITY_OPTIONS: tuple[str, ...] = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")


def _coerce_severity(rule: Any, value: Any) -> None:
    current = getattr(rule, "severity", None)
    raw = str(value).upper()
    if raw not in SEVERITY_OPTIONS:
        return
    if isinstance(current, Enum):
        setattr(rule, "severity", type(current)(raw))
    else:
        setattr(rule, "severity", raw)


def apply_rule_overrides(rule: Any, overrides: dict | None) -> None:
    """Mutate *rule* in place with threshold and severity overrides."""
    if not overrides:
        return
    for key, value in overrides.items():
        if key == "severity":
            if hasattr(rule, "severity"):
                _coerce_severity(rule, value)
            continue
        if hasattr(rule, key):
            setattr(rule, key, value)
