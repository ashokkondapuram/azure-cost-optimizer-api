"""Azure Retail Prices API — on-demand SKU pricing for savings estimates.

Public API (no auth): https://prices.azure.com/api/retail/prices
Docs: https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Literal

import requests
import structlog

log = structlog.get_logger()

RETAIL_PRICES_BASE = "https://prices.azure.com/api/retail/prices"
HOURS_PER_MONTH = 730

_retail_request_lock = threading.Lock()
_last_retail_request_at = 0.0

_CACHE: dict[str, tuple[float, Any]] = {}
_NEGATIVE_CACHE: dict[str, float] = {}
_CACHE_TTL_SECONDS = 3600
_NEGATIVE_CACHE_TTL_SECONDS = 300


def _float_env(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def retail_price_query_delay_sec() -> float:
    """Minimum pause between Retail Prices API calls (429 avoidance)."""
    return _float_env("RETAIL_PRICE_QUERY_DELAY_SEC", 0.5)


def retail_price_max_retries() -> int:
    return _int_env("RETAIL_PRICE_MAX_RETRIES", 5)


def retail_price_retry_base_sec() -> float:
    return _float_env("RETAIL_PRICE_RETRY_BASE_SEC", 2.0)


def _pause_between_retail_requests(label: str = "query") -> None:
    """Serialize retail pricing traffic with a configurable gap between calls."""
    global _last_retail_request_at
    delay = retail_price_query_delay_sec()
    with _retail_request_lock:
        elapsed = time.monotonic() - _last_retail_request_at
        if elapsed < delay:
            wait = delay - elapsed
            log.debug("azure_retail_prices.throttle_wait", seconds=round(wait, 2), phase=label)
            time.sleep(wait)
        _last_retail_request_at = time.monotonic()

# Premium SSD / Standard SSD managed disk size → retail SKU code (GiB threshold)
_PREMIUM_DISK_CODE: dict[int, str] = {
    4: "P4", 8: "P6", 16: "P10", 32: "P15", 64: "P20", 128: "P30",
    256: "P40", 512: "P50", 1024: "P60", 2048: "P70", 4096: "P80",
}
_STANDARD_SSD_DISK_CODE: dict[int, str] = {
    4: "E4", 8: "E6", 16: "E10", 32: "E15", 64: "E20", 128: "E30",
    256: "E40", 512: "E50", 1024: "E60", 2048: "E70", 4096: "E80",
}
_DISK_TIER_SIZES = sorted(_PREMIUM_DISK_CODE.keys())


def _cache_get(key: str) -> Any | None:
    row = _CACHE.get(key)
    if not row:
        return None
    expires_at, value = row
    if time.monotonic() > expires_at:
        _CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: Any) -> None:
    _CACHE[key] = (time.monotonic() + _CACHE_TTL_SECONDS, value)


def _normalize_retail_region(region: str | None) -> str:
    """ARM region slug for Retail Prices API filters (no spaces, lowercase)."""
    return (region or "").strip().replace(" ", "").lower()


def _odata_escape(value: str) -> str:
    return (value or "").replace("'", "''")


def _negative_cache_hit(key: str) -> bool:
    expires_at = _NEGATIVE_CACHE.get(key)
    if expires_at is None:
        return False
    if time.monotonic() > expires_at:
        _NEGATIVE_CACHE.pop(key, None)
        return False
    return True


def _negative_cache_set(key: str) -> None:
    _NEGATIVE_CACHE[key] = time.monotonic() + _NEGATIVE_CACHE_TTL_SECONDS


def _retry_after_seconds(response: requests.Response, attempt: int) -> float:
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return max(1.0, float(raw))
        except (TypeError, ValueError):
            pass
    return retail_price_retry_base_sec() * (2 ** attempt)


def _get_retail_page(url: str, *, params: dict[str, str] | None, label: str) -> requests.Response:
    """GET one retail prices page with throttle and 429 retries."""
    max_retries = retail_price_max_retries()
    for attempt in range(max_retries):
        _pause_between_retail_requests(label)
        resp = requests.get(url, params=params, timeout=45)
        if resp.status_code != 429:
            return resp
        wait = _retry_after_seconds(resp, attempt)
        log.warning(
            "azure_retail_prices_rate_limited",
            url=url,
            attempt=attempt + 1,
            max_retries=max_retries,
            wait_seconds=round(wait, 1),
        )
        time.sleep(wait)
    return resp


def _fetch_retail_items(filter_expr: str) -> list[dict[str, Any]]:
    cache_key = f"filter:{filter_expr}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    if _negative_cache_hit(cache_key):
        return []

    items: list[dict[str, Any]] = []
    url: str | None = RETAIL_PRICES_BASE
    params: dict[str, str] | None = {"$filter": filter_expr}
    page = 0
    try:
        while url:
            page += 1
            resp = _get_retail_page(url, params=params, label=f"filter_page_{page}")
            if resp.status_code == 429:
                _negative_cache_set(cache_key)
                log.warning(
                    "azure_retail_prices_fetch_failed",
                    filter=filter_expr,
                    error="429 Too Many Requests after retries",
                )
                return []
            resp.raise_for_status()
            payload = resp.json()
            items.extend(payload.get("Items") or [])
            url = payload.get("NextPageLink")
            params = None
    except Exception as exc:
        log.warning("azure_retail_prices_fetch_failed", filter=filter_expr, error=str(exc))
        if "429" in str(exc):
            _negative_cache_set(cache_key)
        return []

    _cache_set(cache_key, items)
    return items


def _pick_hourly_price(
    items: list[dict[str, Any]],
    *,
    os_type: str | None = None,
    spot_only: bool = False,
) -> float | None:
    """Select best hourly meter from retail price rows."""
    os_norm = (os_type or "linux").lower()
    prices: list[float] = []
    for item in items:
        if (item.get("priceType") or item.get("type") or "").lower() != "consumption":
            continue
        if (item.get("unitOfMeasure") or "") != "1 Hour":
            continue
        product = (item.get("productName") or "").lower()
        sku = (item.get("skuName") or "").lower()
        meter = (item.get("meterName") or "").lower()
        combined = f"{product} {sku} {meter}"
        is_spot = "spot" in combined or "low priority" in combined or "lowpriority" in combined
        if spot_only:
            if not is_spot:
                continue
        elif is_spot or any(x in combined for x in ("devtest", "savings plan")):
            continue
        if os_norm == "linux":
            if "windows" in product and "linux" not in product:
                continue
        elif os_norm == "windows":
            if "windows" not in product:
                continue
        price = item.get("retailPrice")
        if price is None:
            price = item.get("unitPrice")
        if price is not None:
            try:
                prices.append(float(price))
            except (TypeError, ValueError):
                continue
    if not prices:
        return None
    return min(prices)


def _pick_monthly_price(items: list[dict[str, Any]], *, sku_fragment: str = "") -> float | None:
    prices: list[float] = []
    frag = sku_fragment.lower()
    for item in items:
        if frag and frag not in (item.get("skuName") or "").lower() and frag not in (item.get("productName") or "").lower():
            continue
        unit = item.get("unitOfMeasure") or ""
        price = item.get("retailPrice") or item.get("unitPrice")
        if price is None:
            continue
        try:
            val = float(price)
        except (TypeError, ValueError):
            continue
        if unit == "1 Month":
            prices.append(val)
        elif unit == "1 Hour":
            prices.append(val * HOURS_PER_MONTH)
    return round(min(prices), 2) if prices else None


def vm_os_type(resource: dict[str, Any]) -> Literal["linux", "windows"]:
    props = resource.get("properties") or {}
    os_type = ((props.get("storageProfile") or {}).get("osDisk") or {}).get("osType") or "Linux"
    return "windows" if str(os_type).lower() == "windows" else "linux"


def get_vm_hourly_price(
    region: str,
    sku: str,
    *,
    os_type: str = "linux",
) -> float | None:
    """On-demand hourly price for a VM SKU in a region (Azure Retail Prices)."""
    loc = _normalize_retail_region(region)
    arm_sku = (sku or "").strip()
    if not loc or not arm_sku:
        return None

    cache_key = f"vm:{loc}:{arm_sku.lower()}:{os_type.lower()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    filt = (
        f"serviceName eq 'Virtual Machines' and armRegionName eq '{_odata_escape(loc)}' "
        f"and armSkuName eq '{_odata_escape(arm_sku)}' and priceType eq 'Consumption'"
    )
    hourly = _pick_hourly_price(_fetch_retail_items(filt), os_type=os_type)
    if hourly is not None:
        _cache_set(cache_key, hourly)
    return hourly


def get_vm_monthly_price(
    region: str,
    sku: str,
    *,
    os_type: str = "linux",
) -> float | None:
    hourly = get_vm_hourly_price(region, sku, os_type=os_type)
    if hourly is None:
        return None
    return round(hourly * HOURS_PER_MONTH, 2)


def estimate_vm_sku_savings(
    region: str,
    current_sku: str,
    suggested_sku: str,
    *,
    os_type: str = "linux",
    actual_monthly_cost: float | None = None,
    monthly_run_rate_usd: float | None = None,
) -> dict[str, Any]:
    """
    Compute monthly savings from Azure retail on-demand pricing.

    Retail list-price delta is always computed. When billed MTD cost or a monthly
    run-rate is available, primary savings use run-rate × (1 − target/current retail).
    """
    from app.cost_utils import project_mtd_to_monthly_run_rate

    current_retail = get_vm_monthly_price(region, current_sku, os_type=os_type)
    suggested_retail = get_vm_monthly_price(region, suggested_sku, os_type=os_type)

    retail_savings = 0.0
    retail_ratio: float | None = None
    if current_retail is not None and suggested_retail is not None and current_retail > 0:
        retail_savings = max(0.0, round(current_retail - suggested_retail, 2))
        retail_ratio = suggested_retail / current_retail

    run_rate = monthly_run_rate_usd
    if run_rate is None and actual_monthly_cost and actual_monthly_cost > 0:
        run_rate = project_mtd_to_monthly_run_rate(actual_monthly_cost)

    run_rate_savings = 0.0
    if run_rate and run_rate > 0 and retail_ratio is not None:
        run_rate_savings = max(0.0, round(run_rate * (1.0 - retail_ratio), 2))

    if run_rate and run_rate > 0 and retail_ratio is not None:
        savings = run_rate_savings
        savings_basis = "monthly_run_rate"
    else:
        savings = retail_savings
        savings_basis = "retail_list"

    payload = {
        "current_sku_monthly_usd": current_retail,
        "suggested_sku_monthly_usd": suggested_retail,
        "estimated_monthly_savings_usd": savings,
        "retail_monthly_savings_usd": retail_savings,
        "run_rate_monthly_savings_usd": run_rate_savings if run_rate else None,
        "mtd_cost_usd": actual_monthly_cost,
        "monthly_run_rate_usd": run_rate,
        "actual_mtd_cost_usd": actual_monthly_cost,
        "savings_basis": savings_basis,
        "retail_price_ratio": round(retail_ratio, 6) if retail_ratio is not None else None,
        "pricing_source": "azure_retail_prices",
        "pricing_model": "consumption",
        "hours_per_month": HOURS_PER_MONTH,
        "os_type": os_type,
    }
    payload["pricing_status"] = "available" if current_retail is not None and suggested_retail is not None else "unavailable"
    return payload


def _disk_billed_size_gb(size_gb: int | float) -> int:
    size = max(4, int(size_gb or 4))
    for tier in _DISK_TIER_SIZES:
        if size <= tier:
            return tier
    return _DISK_TIER_SIZES[-1]


def _managed_disk_retail_sku(tier: str, size_gb: int | float) -> tuple[str, str]:
    billed = _disk_billed_size_gb(size_gb)
    if tier == "premium":
        code = _PREMIUM_DISK_CODE.get(billed, "P30")
        product_fragment = "Premium SSD Managed Disks"
    elif tier == "standard_ssd":
        code = _STANDARD_SSD_DISK_CODE.get(billed, "E30")
        product_fragment = "Standard SSD Managed Disks"
    else:
        code = "S30"
        product_fragment = "Standard HDD Managed Disks"
    return code, product_fragment


def get_managed_disk_monthly_price(
    region: str,
    *,
    size_gb: int | float,
    tier: Literal["premium", "standard_ssd", "standard_hdd"] = "premium",
) -> float | None:
    loc = _normalize_retail_region(region)
    if not loc:
        return None

    code, product_fragment = _managed_disk_retail_sku(tier, size_gb)
    cache_key = f"disk:{loc}:{tier}:{code}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    filt = (
        f"serviceName eq 'Storage' and armRegionName eq '{_odata_escape(loc)}' "
        f"and priceType eq 'Consumption' and contains(productName,'{_odata_escape(product_fragment)}') "
        f"and contains(skuName,'{_odata_escape(code)}')"
    )
    items = _fetch_retail_items(filt)
    monthly_prices: list[float] = []
    for item in items:
        if (item.get("unitOfMeasure") or "") != "1 Month":
            continue
        price = item.get("retailPrice") or item.get("unitPrice")
        if price is not None:
            try:
                monthly_prices.append(float(price))
            except (TypeError, ValueError):
                continue
    if not monthly_prices:
        # Some regions publish per-GB/month meters
        for item in items:
            if "GB" in (item.get("unitOfMeasure") or ""):
                price = item.get("retailPrice") or item.get("unitPrice")
                if price is not None:
                    try:
                        monthly_prices.append(float(price) * _disk_billed_size_gb(size_gb))
                    except (TypeError, ValueError):
                        continue
    if not monthly_prices:
        return None
    monthly = round(min(monthly_prices), 2)
    _cache_set(cache_key, monthly)
    return monthly


def estimate_disk_tier_savings(
    region: str,
    size_gb: int | float,
    current_tier: str,
    suggested_tier: str,
    *,
    actual_monthly_cost: float | None = None,
) -> dict[str, Any]:
    """Savings from moving managed disk to a lower tier using Azure retail prices."""
    tier_map = {
        "premium": "premium",
        "premium_lrs": "premium",
        "premium_zrs": "premium",
        "standardssd": "standard_ssd",
        "standardssd_lrs": "standard_ssd",
        "standard_ssd": "standard_ssd",
        "standard": "standard_hdd",
        "standard_lrs": "standard_hdd",
        "standard_hdd": "standard_hdd",
    }
    cur_key = tier_map.get((current_tier or "").lower().replace("_", "").replace(" ", ""), "premium")
    sug_key = tier_map.get((suggested_tier or "").lower().replace("_", "").replace(" ", ""), "standard_ssd")

    current_retail = get_managed_disk_monthly_price(region, size_gb=size_gb, tier=cur_key)  # type: ignore[arg-type]
    suggested_retail = get_managed_disk_monthly_price(region, size_gb=size_gb, tier=sug_key)  # type: ignore[arg-type]

    retail_savings = 0.0
    if current_retail is not None and suggested_retail is not None:
        retail_savings = max(0.0, round(current_retail - suggested_retail, 2))

    savings = retail_savings
    if actual_monthly_cost and actual_monthly_cost > 0:
        if current_retail and current_retail > 0 and suggested_retail is not None:
            savings = max(0.0, round(actual_monthly_cost * (1.0 - suggested_retail / current_retail), 2))
        else:
            from app.managed_disk_catalog import disk_type_spec

            cur_rel = float(disk_type_spec(current_tier).get("relative_cost") or 1.0)
            sug_rel = float(disk_type_spec(suggested_tier).get("relative_cost") or 1.0)
            if cur_rel > sug_rel > 0:
                savings = max(0.0, round(actual_monthly_cost * (1.0 - sug_rel / cur_rel), 2))

    return {
        "current_tier": current_tier,
        "suggested_tier": suggested_tier,
        "size_gb": size_gb,
        "current_tier_monthly_usd": current_retail,
        "suggested_tier_monthly_usd": suggested_retail,
        "estimated_monthly_savings_usd": savings,
        "retail_monthly_savings_usd": retail_savings,
        "actual_mtd_cost_usd": actual_monthly_cost,
        "pricing_source": "azure_billed_mtd" if actual_monthly_cost and actual_monthly_cost > 0 else "azure_retail_prices",
        "pricing_status": "available" if (actual_monthly_cost and actual_monthly_cost > 0) or (
            current_retail is not None and suggested_retail is not None
        ) else "unavailable",
    }


def get_vm_spot_hourly_price(
    region: str,
    sku: str,
    *,
    os_type: str = "linux",
) -> float | None:
    loc = _normalize_retail_region(region)
    arm_sku = (sku or "").strip()
    if not loc or not arm_sku:
        return None
    cache_key = f"vm_spot:{loc}:{arm_sku.lower()}:{os_type.lower()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    filt = (
        f"serviceName eq 'Virtual Machines' and armRegionName eq '{_odata_escape(loc)}' "
        f"and armSkuName eq '{_odata_escape(arm_sku)}' and priceType eq 'Consumption'"
    )
    hourly = _pick_hourly_price(_fetch_retail_items(filt), os_type=os_type, spot_only=True)
    if hourly is not None:
        _cache_set(cache_key, hourly)
    return hourly


def estimate_aks_spot_savings(
    region: str,
    vm_sku: str,
    node_count: int,
    *,
    os_type: str = "linux",
    actual_monthly_cost: float | None = None,
) -> dict[str, Any]:
    """Retail on-demand vs Spot delta for an AKS node pool."""
    count = max(1, int(node_count or 1))
    on_demand = get_vm_monthly_price(region, vm_sku, os_type=os_type)
    spot_hourly = get_vm_spot_hourly_price(region, vm_sku, os_type=os_type)
    spot_monthly = round(spot_hourly * HOURS_PER_MONTH, 2) if spot_hourly else None
    current = round(on_demand * count, 2) if on_demand else None
    suggested = round(spot_monthly * count, 2) if spot_monthly else None
    retail_savings = max(0.0, round((current or 0) - (suggested or 0), 2)) if current and suggested else 0.0
    savings = retail_savings
    if actual_monthly_cost and actual_monthly_cost > 0 and current and current > 0 and suggested is not None:
        savings = max(0.0, round(actual_monthly_cost * (1.0 - suggested / current), 2))
    return {
        "current_sku_monthly_usd": current,
        "suggested_sku_monthly_usd": suggested,
        "estimated_monthly_savings_usd": savings,
        "retail_monthly_savings_usd": retail_savings,
        "actual_mtd_cost_usd": actual_monthly_cost,
        "pricing_source": "azure_retail_prices",
        "pricing_model": "spot_vs_on_demand",
        "node_count": count,
        "vm_size": vm_sku,
        "pricing_status": "available" if current is not None and suggested is not None else "unavailable",
    }


def _service_monthly_price(
    region: str,
    service_name: str,
    sku_fragment: str,
    *,
    cache_prefix: str,
) -> float | None:
    loc = _normalize_retail_region(region)
    if not loc or not sku_fragment:
        return None
    cache_key = f"{cache_prefix}:{loc}:{sku_fragment.lower()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    filt = (
        f"serviceName eq '{_odata_escape(service_name)}' and armRegionName eq '{_odata_escape(loc)}' "
        f"and priceType eq 'Consumption'"
    )
    monthly = _pick_monthly_price(_fetch_retail_items(filt), sku_fragment=sku_fragment)
    if monthly is not None:
        _cache_set(cache_key, monthly)
    return monthly


_APP_SERVICE_TIER_MAP = {
    "premiumv3": "P1 v3",
    "premiumv2": "P1 v2",
    "premium": "P1",
    "standard": "S1",
    "basic": "B1",
    "isolated": "I1",
}


def estimate_app_service_tier_savings(
    region: str,
    current_tier: str,
    suggested_tier: str,
    *,
    actual_monthly_cost: float | None = None,
) -> dict[str, Any]:
    cur_frag = _APP_SERVICE_TIER_MAP.get((current_tier or "").lower(), current_tier)
    sug_frag = _APP_SERVICE_TIER_MAP.get((suggested_tier or "").lower(), suggested_tier)
    current = _service_monthly_price(region, "Azure App Service", cur_frag, cache_prefix="asp")
    suggested = _service_monthly_price(region, "Azure App Service", sug_frag, cache_prefix="asp")
    retail_savings = max(0.0, round((current or 0) - (suggested or 0), 2)) if current and suggested else 0.0
    savings = retail_savings
    if actual_monthly_cost and actual_monthly_cost > 0 and current and current > 0 and suggested is not None:
        savings = max(0.0, round(actual_monthly_cost * (1.0 - suggested / current), 2))
    return {
        "current_tier": current_tier,
        "suggested_tier": suggested_tier,
        "current_sku_monthly_usd": current,
        "suggested_sku_monthly_usd": suggested,
        "estimated_monthly_savings_usd": savings,
        "retail_monthly_savings_usd": retail_savings,
        "actual_mtd_cost_usd": actual_monthly_cost,
        "pricing_source": "azure_retail_prices",
        "pricing_status": "available" if current is not None and suggested is not None else "unavailable",
    }


def estimate_cosmos_throughput_savings(
    region: str,
    current_model: str,
    suggested_model: str,
    *,
    actual_monthly_cost: float | None = None,
) -> dict[str, Any]:
    """Retail pricing for Cosmos DB throughput model transitions."""
    return estimate_service_tier_savings(
        region,
        "Azure Cosmos DB",
        current_model,
        suggested_model,
        cache_prefix="cosmos",
        actual_monthly_cost=actual_monthly_cost,
    )


def estimate_postgresql_tier_savings(
    region: str,
    current_sku: str,
    suggested_sku: str,
    *,
    actual_monthly_cost: float | None = None,
) -> dict[str, Any]:
    current = _service_monthly_price(region, "Azure Database for PostgreSQL", current_sku, cache_prefix="pg")
    suggested = _service_monthly_price(region, "Azure Database for PostgreSQL", suggested_sku, cache_prefix="pg")
    retail_savings = max(0.0, round((current or 0) - (suggested or 0), 2)) if current and suggested else 0.0
    savings = retail_savings
    if actual_monthly_cost and actual_monthly_cost > 0 and current and current > 0 and suggested is not None:
        savings = max(0.0, round(actual_monthly_cost * (1.0 - suggested / current), 2))
    return {
        "current_sku_monthly_usd": current,
        "suggested_sku_monthly_usd": suggested,
        "estimated_monthly_savings_usd": savings,
        "pricing_source": "azure_retail_prices",
        "pricing_status": "available" if current is not None and suggested is not None else "unavailable",
    }


def estimate_postgresql_ha_savings(
    actual_monthly_cost: float,
    ha_mode: str | None,
    *,
    disable: bool = True,
) -> float:
    """Estimate monthly savings from disabling HA on a PostgreSQL flexible server."""
    from app.postgresql_sku_catalog import ha_mode_spec

    if actual_monthly_cost <= 0 or not disable:
        return 0.0
    multiplier = float(ha_mode_spec(ha_mode).get("cost_multiplier") or 1.0)
    if multiplier <= 1.0:
        return 0.0
    base_cost = actual_monthly_cost / multiplier
    return max(0.0, round(actual_monthly_cost - base_cost, 2))


def estimate_redis_tier_transition(
    region: str,
    current_tier: str,
    current_capacity: int,
    suggested_tier: str,
    suggested_capacity: int,
    *,
    actual_monthly_cost: float | None = None,
) -> dict[str, Any]:
    """Retail pricing for arbitrary Redis tier/capacity transitions."""
    cur_frag = f"{current_tier} C{current_capacity}"
    sug_frag = f"{suggested_tier} C{suggested_capacity}"
    current = _service_monthly_price(region, "Redis Cache", cur_frag, cache_prefix="redis")
    suggested = _service_monthly_price(region, "Redis Cache", sug_frag, cache_prefix="redis")
    retail_savings = max(0.0, round((current or 0) - (suggested or 0), 2)) if current and suggested else 0.0
    savings = retail_savings
    if actual_monthly_cost and actual_monthly_cost > 0 and current and current > 0 and suggested is not None:
        savings = max(0.0, round(actual_monthly_cost * (1.0 - suggested / current), 2))
    return {
        "current_tier": current_tier,
        "suggested_tier": suggested_tier,
        "current_capacity": current_capacity,
        "suggested_capacity": suggested_capacity,
        "current_sku_monthly_usd": current,
        "suggested_sku_monthly_usd": suggested,
        "estimated_monthly_savings_usd": savings,
        "pricing_source": "azure_retail_prices",
        "pricing_status": "available" if current is not None and suggested is not None else "unavailable",
    }


def estimate_redis_tier_savings(
    region: str,
    current_capacity: int,
    suggested_capacity: int,
    *,
    tier: str = "Premium",
    actual_monthly_cost: float | None = None,
) -> dict[str, Any]:
    return estimate_redis_tier_transition(
        region,
        tier,
        current_capacity,
        "Standard",
        suggested_capacity,
        actual_monthly_cost=actual_monthly_cost,
    )


def estimate_service_tier_savings(
    region: str,
    service_name: str,
    current_fragment: str,
    suggested_fragment: str,
    *,
    cache_prefix: str,
    actual_monthly_cost: float | None = None,
) -> dict[str, Any]:
    """Generic retail tier/SKU savings for PaaS services."""
    current = _service_monthly_price(region, service_name, current_fragment, cache_prefix=cache_prefix)
    suggested = _service_monthly_price(region, service_name, suggested_fragment, cache_prefix=cache_prefix)
    retail_savings = max(0.0, round((current or 0) - (suggested or 0), 2)) if current and suggested else 0.0
    savings = retail_savings
    if actual_monthly_cost and actual_monthly_cost > 0 and current and current > 0 and suggested is not None:
        savings = max(0.0, round(actual_monthly_cost * (1.0 - suggested / current), 2))
    return {
        "current_sku_monthly_usd": current,
        "suggested_sku_monthly_usd": suggested,
        "estimated_monthly_savings_usd": savings,
        "pricing_source": "azure_retail_prices",
        "pricing_status": "available" if current is not None and suggested is not None else "unavailable",
    }


def estimate_nat_gateway_monthly_price(*, public_ip_count: int = 1) -> dict[str, Any]:
    """Catalog-based NAT Gateway hourly/monthly baseline (gateway + public IPs)."""
    from app.network_pricing import estimate_nat_gateway_hourly, monthly_from_hourly

    hourly = estimate_nat_gateway_hourly(public_ip_count)
    monthly = monthly_from_hourly(hourly)
    return {
        "hourly_usd": hourly,
        "estimated_monthly_usd": monthly,
        "public_ip_count": max(1, int(public_ip_count or 1)),
        "pricing_source": "catalog_thresholds",
        "pricing_status": "available",
    }


def estimate_load_balancer_monthly_price() -> dict[str, Any]:
    """Catalog-based Standard load balancer hourly/monthly baseline."""
    from app.network_pricing import estimate_load_balancer_hourly, monthly_from_hourly

    hourly = estimate_load_balancer_hourly()
    monthly = monthly_from_hourly(hourly)
    return {
        "hourly_usd": hourly,
        "estimated_monthly_usd": monthly,
        "pricing_source": "catalog_thresholds",
        "pricing_status": "available",
    }


def estimate_app_gateway_monthly_price(
    *,
    tier: str = "Standard_v2",
    capacity: int = 1,
) -> dict[str, Any]:
    """Catalog-based Application Gateway v2 fixed + capacity unit monthly baseline."""
    from app.app_gateway_catalog import tier_spec
    from app.network_pricing import monthly_from_hourly

    meta = tier_spec(tier)
    fixed_hourly = float(meta.get("fixed_cost_hourly_usd") or 0.0)
    unit_hourly = float(meta.get("capacity_unit_hourly_usd") or 0.0)
    cap = max(1, int(capacity or 1))
    hourly = fixed_hourly + unit_hourly * cap
    monthly = monthly_from_hourly(hourly)
    return {
        "sku_tier": tier,
        "capacity": cap,
        "hourly_usd": round(hourly, 4),
        "estimated_monthly_usd": monthly,
        "pricing_source": "catalog_thresholds",
        "pricing_status": "available",
    }
