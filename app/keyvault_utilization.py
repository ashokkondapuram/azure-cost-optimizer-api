"""Key Vault API activity, protection baseline, and SKU helpers for cost rules."""

from __future__ import annotations

from typing import Any

from app.metrics_triggers import TRAFFIC_THRESHOLDS
from app.resource_utilization import fact_value


def _props(vault: dict[str, Any]) -> dict[str, Any]:
    return dict(vault.get("properties") or {})


def kv_sku_name(vault: dict[str, Any]) -> str:
    facts = vault.get("_technical_facts") or {}
    raw = facts.get("sku")
    if raw:
        return str(raw).lower()
    sku = vault.get("sku") or _props(vault).get("sku") or {}
    if isinstance(sku, dict):
        return str(sku.get("name") or "").lower()
    return str(sku or "").lower()


def soft_delete_enabled(vault: dict[str, Any]) -> bool | None:
    facts = vault.get("_technical_facts") or {}
    raw = facts.get("soft_delete_enabled")
    if raw is not None:
        return bool(raw)
    val = _props(vault).get("enableSoftDelete")
    return bool(val) if val is not None else None


def purge_protection_enabled(vault: dict[str, Any]) -> bool:
    facts = vault.get("_technical_facts") or {}
    raw = facts.get("purge_protection_enabled")
    if raw is not None:
        return bool(raw)
    return _props(vault).get("enablePurgeProtection") is True


def protection_baseline_gap(vault: dict[str, Any]) -> bool:
    soft = soft_delete_enabled(vault)
    purge = purge_protection_enabled(vault)
    return soft is False or not purge


def is_idle_keyvault(
    vault: dict[str, Any],
    *,
    threshold: float | None = None,
) -> bool | None:
    hits = fact_value(vault, "api_hits")
    if hits is None:
        return None
    limit = threshold if threshold is not None else TRAFFIC_THRESHOLDS["kv_api_hits_idle"]
    return float(hits) < limit


def is_high_keyvault_ops(
    vault: dict[str, Any],
    *,
    threshold: float | None = None,
) -> bool | None:
    hits = fact_value(vault, "api_hits")
    if hits is None:
        return None
    limit = threshold if threshold is not None else TRAFFIC_THRESHOLDS["kv_api_hits_high"]
    return float(hits) >= limit


def meets_kv_savings_gate(
    monthly_cost: float,
    *,
    min_monthly_savings_usd: float | None = None,
) -> bool:
    minimum = min_monthly_savings_usd if min_monthly_savings_usd is not None else 0.0
    return monthly_cost >= minimum


def is_nonprod_vault(vault: dict[str, Any], *, nonprod_values: list[str] | tuple[str, ...]) -> bool:
    tags = vault.get("tags") or {}
    env = str(tags.get("environment") or tags.get("env") or "").lower()
    if not env:
        return True
    return env in {v.lower() for v in nonprod_values}


def blocks_premium_downgrade(
    vault: dict[str, Any],
    *,
    nonprod_values: list[str] | tuple[str, ...] | None = None,
    idle_threshold: float | None = None,
) -> bool:
    if nonprod_values is not None and not is_nonprod_vault(vault, nonprod_values=nonprod_values):
        return True
    hits = fact_value(vault, "api_hits")
    if hits is not None:
        limit = idle_threshold if idle_threshold is not None else TRAFFIC_THRESHOLDS["kv_api_hits_idle"]
        if float(hits) >= limit * 10:
            return True
    return False


def kv_threshold_evidence(rule) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("kv_api_hits_idle", "kv_api_hits_high", "min_monthly_savings_usd"):
        val = getattr(rule, key, None)
        if val is not None:
            out[key] = val
    return out


def kv_inventory_evidence(vault: dict[str, Any]) -> dict[str, Any]:
    facts = vault.get("_technical_facts") or {}
    props = _props(vault)
    network = props.get("networkAcls") or {}
    out: dict[str, Any] = {
        "sku": kv_sku_name(vault),
        "enableSoftDelete": soft_delete_enabled(vault),
        "enablePurgeProtection": purge_protection_enabled(vault),
        "rbac_enabled": facts.get("rbac_enabled") if facts.get("rbac_enabled") is not None else props.get("enableRbacAuthorization"),
    }
    pna = props.get("publicNetworkAccess")
    if pna not in (None, ""):
        out["public_network_access"] = pna
    default_action = network.get("defaultAction") or facts.get("network_default_action")
    if default_action not in (None, ""):
        out["network_default_action"] = default_action
    hits = fact_value(vault, "api_hits")
    if hits is not None:
        out["api_hits"] = hits
    return out
