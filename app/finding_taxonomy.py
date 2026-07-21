"""Shared finding category/severity ordering and display labels."""
from __future__ import annotations

from typing import Any, Iterable

SEVERITY_ORDER: tuple[str, ...] = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")

SEVERITY_LABELS: dict[str, str] = {
    "CRITICAL": "Critical",
    "HIGH": "High",
    "MEDIUM": "Medium",
    "LOW": "Low",
    "INFO": "Info",
}

CATEGORY_ORDER: tuple[str, ...] = (
    "COMPUTE",
    "KUBERNETES",
    "STORAGE",
    "NETWORK",
    "DATABASE",
    "SECURITY",
    "COST",
    "GOVERNANCE",
    "RELIABILITY",
    "OTHER",
)

CATEGORY_LABELS: dict[str, str] = {
    "COMPUTE": "Compute",
    "KUBERNETES": "Kubernetes",
    "STORAGE": "Storage",
    "NETWORK": "Network",
    "DATABASE": "Database",
    "SECURITY": "Security",
    "COST": "Cost",
    "GOVERNANCE": "Governance",
    "RELIABILITY": "Reliability",
    "OTHER": "Other",
}

SOURCE_ORDER: tuple[str, ...] = (
    "cost_performance",
    "reliability_security",
    "governance",
)

SOURCE_LABELS: dict[str, str] = {
    "cost_performance": "Cost & performance",
    "reliability_security": "Reliability & security",
    "governance": "Governance",
}

_CANONICAL_PREFIX_TO_CATEGORY: dict[str, str] = {
    "compute": "COMPUTE",
    "containers": "KUBERNETES",
    "storage": "STORAGE",
    "network": "NETWORK",
    "database": "DATABASE",
    "appservice": "COMPUTE",
    "security": "SECURITY",
    "monitoring": "GOVERNANCE",
    "integration": "GOVERNANCE",
    "messaging": "GOVERNANCE",
    "analytics": "DATABASE",
    "backup": "STORAGE",
    "automation": "GOVERNANCE",
    "search": "DATABASE",
}

_SEVERITY_RANK = {key: index for index, key in enumerate(SEVERITY_ORDER)}
_CATEGORY_RANK = {key: index for index, key in enumerate(CATEGORY_ORDER)}
_SOURCE_RANK = {key: index for index, key in enumerate(SOURCE_ORDER)}


def normalize_severity(value: str | None) -> str:
    key = str(value or "INFO").strip().upper()
    return key if key in _SEVERITY_RANK else "INFO"


def normalize_category(value: str | None) -> str:
    key = str(value or "OTHER").strip().upper()
    if key in _CATEGORY_RANK:
        return key
    return "OTHER"


def format_severity_label(severity: str | None) -> str:
    key = normalize_severity(severity)
    return SEVERITY_LABELS.get(key, key.title())


def format_category_label(category: str | None) -> str:
    key = normalize_category(category)
    if key in CATEGORY_LABELS:
        return CATEGORY_LABELS[key]
    lower = key.lower()
    return lower[:1].upper() + lower[1:] if lower else "Other"


def format_source_label(source: str | None) -> str:
    key = str(source or "").strip().lower()
    if key in SOURCE_LABELS:
        return SOURCE_LABELS[key]
    return key.replace("_", " ").title() if key else "Other"


def category_from_resource_type(resource_type: str | None) -> str:
    token = str(resource_type or "").strip().lower()
    if not token:
        return "OTHER"
    prefix = token.split("/")[0] if "/" in token else token
    return _CANONICAL_PREFIX_TO_CATEGORY.get(prefix, "OTHER")


def severity_rank(severity: str | None) -> int:
    return _SEVERITY_RANK.get(normalize_severity(severity), len(SEVERITY_ORDER))


def category_rank(category: str | None) -> int:
    return _CATEGORY_RANK.get(normalize_category(category), len(CATEGORY_ORDER))


def build_ordered_breakdown(
    counts: dict[str, int],
    *,
    savings: dict[str, float] | None = None,
    kind: str = "category",
) -> list[dict[str, Any]]:
    """Return [{key, label, count, estimated_savings_usd}] in stable display order."""
    if kind == "severity":
        order = SEVERITY_ORDER
        labels = SEVERITY_LABELS
        label_fn = format_severity_label
    elif kind == "source":
        order = SOURCE_ORDER
        labels = SOURCE_LABELS
        label_fn = format_source_label
    else:
        order = CATEGORY_ORDER
        labels = CATEGORY_LABELS
        label_fn = format_category_label
    savings = savings or {}
    seen = set()
    rows: list[dict[str, Any]] = []
    for key in order:
        count = int(counts.get(key) or 0)
        if count <= 0:
            continue
        seen.add(key)
        rows.append({
            "key": key,
            "label": label_fn(key) if kind in {"category", "source"} else labels.get(key, key.title()),
            "count": count,
            "estimated_savings_usd": round(float(savings.get(key) or 0), 2),
        })
    extras = sorted(
        (k for k in counts if k not in seen and int(counts.get(k) or 0) > 0),
        key=lambda k: (-int(counts.get(k) or 0), k),
    )
    for key in extras:
        count = int(counts.get(key) or 0)
        rows.append({
            "key": key,
            "label": label_fn(key) if kind in {"category", "source"} else format_severity_label(key),
            "count": count,
            "estimated_savings_usd": round(float(savings.get(key) or 0), 2),
        })
    return rows


def sort_findings_by_priority(
    findings: Iterable[Any],
    *,
    savings_attr: str = "estimated_savings_usd",
) -> list[Any]:
    """Sort findings: severity asc, savings desc, detected_at desc."""

    def _key(item: Any) -> tuple:
        if isinstance(item, dict):
            sev = item.get("severity")
            savings = float(item.get(savings_attr) or 0)
            detected = str(item.get("detected_at") or "")
        else:
            sev = getattr(item, "severity", None)
            savings = float(getattr(item, savings_attr, 0) or 0)
            detected = str(getattr(item, "detected_at", "") or "")
        return (severity_rank(sev), -savings, detected)

    return sorted(findings, key=_key)
