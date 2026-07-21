"""Human-readable labels and evidence formatting for Azure Storage accounts."""

from __future__ import annotations

import re
from typing import Any

from app.resources.types import format_fact_display_value
from app.storage_account_catalog import (
    access_tier_spec,
    load_storage_specifications,
    optimization_thresholds,
    recommendation_text,
    replication_display_name,
)

_GB = 1024**3


def _display_config() -> dict[str, str]:
    specs = load_storage_specifications()
    return dict(specs.get("display") or {})


def missing_display() -> str:
    return _display_config().get("missing_value") or "Not synced"


def format_access_tier(tier: str | None) -> str:
    if tier is None or str(tier).strip() == "":
        return "—"
    spec = access_tier_spec(tier)
    return str(spec.get("display_name") or tier).strip()


def normalize_replication_key(sku_name: str | None) -> str:
    raw = str(sku_name or "").strip().upper()
    if not raw:
        return ""
    if raw.startswith("STANDARD_"):
        return raw
    return f"STANDARD_{raw}"


def format_replication_sku(sku_name: str | None) -> str:
    if not sku_name or not str(sku_name).strip():
        return "—"
    return replication_display_name(sku_name)


def format_storage_fact(fact_key: str, value: Any) -> str:
    """Format a storage metric for UI — None is missing, 0 is explicit zero."""
    if value is None or value == "":
        return missing_display()
    key = (fact_key or "").lower()
    if key in {"used_capacity_bytes", "egress_bytes"}:
        num = float(value)
        if num <= 0:
            cfg = _display_config()
            if key == "used_capacity_bytes":
                return cfg.get("zero_capacity") or "0 GB used"
            return "0 GB"
        return format_fact_display_value(fact_key, value)
    if key == "transaction_count":
        num = float(value)
        if num <= 0:
            return _display_config().get("zero_transactions") or "0 transactions"
        return format_fact_display_value(fact_key, value, "count")
    if key == "storage_pct":
        return format_fact_display_value(fact_key, value, "percent")
    if key in {"access_tier", "accessTier"}:
        return format_access_tier(str(value))
    if key in {"sku", "sku_name"}:
        return format_replication_sku(str(value))
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return format_fact_display_value(fact_key, value)


def format_bytes_threshold_gb(bytes_value: float) -> str:
    gb = float(bytes_value) / _GB
    if gb >= 1:
        return f"{gb:,.0f} GB/month"
    return format_fact_display_value("egress_bytes", bytes_value)


def format_transaction_threshold(count: float) -> str:
    return f"< {int(count):,} transactions/month"


def format_storage_utilization_threshold(pct: float) -> str:
    return f"< {pct:.0f}% utilization"


def storage_lifecycle_recommendation(*, cool_days: int | None = None, archive_days: int | None = None) -> str:
    th = optimization_thresholds()
    return recommendation_text(
        "lifecycle",
        cool_days=int(cool_days if cool_days is not None else th.get("lifecycle_cool_after_days", 30)),
        archive_days=int(archive_days if archive_days is not None else th.get("lifecycle_archive_after_days", 90)),
    )


def storage_cool_tier_recommendation(*, cool_days: int, savings_pct: int) -> str:
    return recommendation_text("cool_tier", cool_days=cool_days, savings_pct=savings_pct)


def storage_egress_recommendation() -> str:
    return recommendation_text("egress")


def storage_redundancy_downgrade_recommendation(target_sku: str = "LRS or ZRS") -> str:
    return recommendation_text("redundancy_downgrade", target_sku=target_sku)


def storage_redundancy_upgrade_recommendation() -> str:
    return recommendation_text("redundancy_upgrade")


def storage_hot_tier_recommendation() -> str:
    return recommendation_text("hot_tier_review")


def make_storage_check(
    signal: str,
    fact_key: str,
    value: Any,
    threshold_display: str,
    *,
    passed: bool,
    status: str | None = None,
) -> dict[str, Any]:
    """Evidence check with human-readable observed/criterion values."""
    from app.resource_utilization import make_check

    if value is None and status is None:
        return make_check(
            signal,
            None,
            threshold_display,
            passed=False,
            status="na",
            value_display=missing_display(),
            threshold_display=threshold_display,
            fact_key=fact_key,
        )
    return make_check(
        signal,
        value,
        threshold_display,
        passed=passed,
        status=status,
        value_display=format_storage_fact(fact_key, value),
        threshold_display=threshold_display,
        fact_key=fact_key,
    )


def enrich_storage_evidence_properties(props: dict[str, Any] | None) -> dict[str, Any]:
    """Add display-friendly storage fields for finding evidence panels."""
    props = dict(props or {})
    tier = props.get("accessTier") or props.get("access_tier")
    if tier:
        props["access_tier_display"] = format_access_tier(str(tier))
    sku = props.get("sku")
    sku_name = sku.get("name") if isinstance(sku, dict) else props.get("sku_name")
    if sku_name:
        props["sku_display"] = format_replication_sku(str(sku_name))
    return props
