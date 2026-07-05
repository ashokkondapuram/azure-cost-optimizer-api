"""Azure Cost Management API — live queries using the cached ARM bearer token."""

from __future__ import annotations

import os
import threading
import time
from typing import Any

import structlog

from app.auth import auth_headers, current_arm_auth, get_token, reload_credential
from app.cost_utils import (
    cost_column_indices,
    normalize_monthly_cost_usd,
    service_name_from_cost_row,
    summarize_cost_response,
)
from app.http_client import BASE, AzureAPIError, _request, clear_cache as clear_arm_cache

log = structlog.get_logger()

COST_API_VERSION = os.getenv("AZURE_COST_API_VERSION", "2024-08-01")
COST_API = "azure_cost_management"

_cost_query_lock = threading.Lock()
_last_cost_query_at = 0.0
_adaptive_multiplier = 1.0


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


def cost_query_delay_sec() -> float:
    """Minimum pause between Cost Management API calls (429 avoidance)."""
    return _float_env("COST_QUERY_DELAY_SEC", 10.0)


def cost_rg_batch_size() -> int:
    """Resource groups per by-resource Cost Management query batch."""
    return _int_env("COST_RG_BATCH_SIZE", 5)


def cost_resource_type_batch_size() -> int:
    """ARM resource types per by-resource Cost Management query batch."""
    return _int_env("COST_RT_BATCH_SIZE", 8)


def cost_page_delay_sec() -> float:
    """Extra pause between paginated Cost Management query pages (after throttle)."""
    return _float_env("COST_PAGE_DELAY_SEC", 4.0)


def cost_429_cooldown_sec() -> float:
    """Extra cooldown when Cost Management returns 429 without Retry-After."""
    return _float_env("COST_429_COOLDOWN_SEC", 45.0)


def cost_adaptive_multiplier() -> float:
    """Backoff factor applied after Cost Management 429 responses."""
    with _cost_query_lock:
        return _adaptive_multiplier


def _record_cost_success() -> None:
    global _adaptive_multiplier
    with _cost_query_lock:
        _adaptive_multiplier = max(1.0, _adaptive_multiplier * 0.9)


def _record_cost_429() -> None:
    global _adaptive_multiplier
    with _cost_query_lock:
        _adaptive_multiplier = min(6.0, _adaptive_multiplier * 1.5)
    try:
        from app.cost_query_cache import record_cost_429

        record_cost_429()
    except Exception:
        pass


def _pause_between_cost_queries(label: str = "query") -> None:
    """Serialize Cost Management traffic with a configurable gap between calls."""
    global _last_cost_query_at
    delay = cost_query_delay_sec() * cost_adaptive_multiplier()
    with _cost_query_lock:
        elapsed = time.monotonic() - _last_cost_query_at
        if elapsed < delay:
            wait = delay - elapsed
            log.info(
                "cost_api.throttle_wait",
                seconds=round(wait, 1),
                phase=label,
                adaptive_multiplier=round(cost_adaptive_multiplier(), 2),
            )
            time.sleep(wait)
        _last_cost_query_at = time.monotonic()


def resource_group_filter(resource_groups: list[str]) -> dict:
    """Cost Management filter for a batch of resource group names."""
    values = [rg.strip() for rg in resource_groups if (rg or "").strip()]
    return {
        "dimensions": {
            "name": "ResourceGroupName",
            "operator": "In",
            "values": values,
        },
    }


def resource_type_filter(arm_resource_types: list[str]) -> dict:
    """Cost Management filter for a batch of ARM resource types."""
    values = sorted({(rt or "").strip().lower() for rt in arm_resource_types if (rt or "").strip()})
    return {
        "dimensions": {
            "name": "ResourceType",
            "operator": "In",
            "values": values,
        },
    }


def merge_query_responses(responses: list[dict]) -> dict:
    """Merge batched Cost Management query responses into one normalized payload."""
    if not responses:
        return normalize_query_response({"properties": {"columns": [], "rows": []}})
    base = responses[0]
    props = base.get("properties") or base
    columns = list(props.get("columns") or [])
    rows: list = []
    for resp in responses:
        page_props = resp.get("properties") or resp
        if not columns:
            columns = list(page_props.get("columns") or [])
        rows.extend(page_props.get("rows") or [])
    merged = {
        "id": base.get("id"),
        "name": base.get("name"),
        "type": base.get("type"),
        "properties": {"columns": columns, "rows": rows},
        "source": COST_API,
    }
    return normalize_query_response(merged)

_COLUMN_ALIASES = {
    "ResourceGroupName": "ResourceGroup",
    "totalCost": "PreTaxCost",
    "totalCostUSD": "CostUSD",
}

# Re-export for callers that still catch export-specific errors during transition.
class CostExportNotConfiguredError(Exception):
    """Cost data is available via Cost Management API — blob export is not required."""


class CostExportReadError(Exception):
    """Failed to read cost data from Azure Cost Management."""


def _normalize_subscription_id(subscription_id: str) -> str:
    return (subscription_id or "").strip().lower()


def _normalize_scope(scope: str, subscription_id: str | None = None) -> str:
    s = (scope or "").strip()
    if s.startswith("/"):
        return s
    sub = _normalize_subscription_id(subscription_id or s)
    return f"/subscriptions/{sub}"


def normalize_query_response(response: dict) -> dict:
    """Normalize Cost Management column names to match DB/sync expectations."""
    props = dict(response.get("properties") or response)
    columns = []
    for col in props.get("columns") or []:
        if isinstance(col, dict):
            name = col.get("name") or ""
            columns.append({**col, "name": _COLUMN_ALIASES.get(name, name)})
        else:
            columns.append({"name": _COLUMN_ALIASES.get(str(col), str(col))})
    props["columns"] = columns
    out = dict(response)
    out["properties"] = props
    out["source"] = COST_API
    return out


def _headers(db=None, token: str | None = None) -> dict:
    if token:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    ctx = current_arm_auth()
    if ctx.get("token"):
        return {"Authorization": f"Bearer {ctx['token']}", "Content-Type": "application/json"}
    return auth_headers(db if db is not None else ctx.get("db"))


def _cost_request(
    method: str,
    url: str,
    headers: dict,
    *,
    params: dict | None = None,
    payload: dict | None = None,
    throttle_label: str = "cost_api",
    _retried: bool = False,
) -> dict:
    _pause_between_cost_queries(throttle_label)
    try:
        data = _request(method, url, headers, params=params, payload=payload)
        _record_cost_success()
        return data
    except AzureAPIError as exc:
        if exc.status == 429:
            _record_cost_429()
            log.warning(
                "cost_api.rate_limited",
                throttle_label=throttle_label,
                adaptive_multiplier=round(cost_adaptive_multiplier(), 2),
            )
        if exc.status == 401 and not _retried:
            log.warning("cost_api.token_refresh", reason="401_from_azure")
            reload_credential()
            clear_arm_cache()
            ctx = current_arm_auth()
            db = ctx.get("db")
            fresh = _headers(db, ctx.get("token") or get_token(db))
            return _cost_request(
                method,
                url,
                fresh,
                params=params,
                payload=payload,
                throttle_label=throttle_label,
                _retried=True,
            )
        raise CostExportReadError(f"Azure Cost Management error [{exc.status}]: {exc.message}") from exc


def _run_query(
    scope: str,
    body: dict,
    *,
    db=None,
    token: str | None = None,
    throttle_label: str = "query",
) -> dict:
    scope_path = _normalize_scope(scope)
    url = f"{BASE}{scope_path}/providers/Microsoft.CostManagement/query"
    params = {"api-version": COST_API_VERSION}
    headers = _headers(db, token)

    data = _cost_request(
        "POST", url, headers, params=params, payload=body, throttle_label=throttle_label,
    )
    props = data.get("properties") or data
    columns = list(props.get("columns") or [])
    rows = list(props.get("rows") or [])
    next_link = props.get("nextLink")
    page_delay = cost_page_delay_sec()
    page_num = 1

    while next_link:
        if page_delay:
            time.sleep(page_delay)
        page_num += 1
        page = _cost_request(
            "POST",
            next_link,
            headers,
            payload=body,
            throttle_label=f"{throttle_label}_page_{page_num}",
        )
        page_props = page.get("properties") or page
        if not columns:
            columns = list(page_props.get("columns") or [])
        rows.extend(page_props.get("rows") or [])
        next_link = page_props.get("nextLink")

    merged = {
        "id": data.get("id"),
        "name": data.get("name"),
        "type": data.get("type"),
        "properties": {"columns": columns, "rows": rows},
        "source": COST_API,
    }
    return normalize_query_response(merged)


def _query_body(
    *,
    timeframe: str = "MonthToDate",
    granularity: str = "None",
    group_by: list[dict] | None = None,
    filter_obj: dict | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict:
    dataset: dict[str, Any] = {
        "granularity": granularity,
        "aggregation": {
            "totalCost": {"name": "PreTaxCost", "function": "Sum"},
            "totalCostUSD": {"name": "CostUSD", "function": "Sum"},
        },
    }
    if group_by:
        dataset["grouping"] = group_by
    if filter_obj:
        dataset["filter"] = filter_obj
    body: dict[str, Any] = {"type": "ActualCost", "dataset": dataset}
    if from_date and to_date:
        body["timeframe"] = "Custom"
        body["timePeriod"] = {"from": from_date[:10], "to": to_date[:10]}
    else:
        body["timeframe"] = timeframe
    return body


def _column_index(columns: list[dict]) -> dict[str, int]:
    return {
        (c.get("name") if isinstance(c, dict) else str(c)): i
        for i, c in enumerate(columns)
    }


def daily_query_to_export_rows(response: dict, *, default_currency: str = "CAD") -> list[dict]:
    """Convert a daily Cost Management query response to normalized export-style rows."""
    props = normalize_query_response(response).get("properties") or {}
    cols = _column_index(props.get("columns") or [])
    if not cols:
        return []

    def _cell(row: list, *names: str, default: Any = "") -> Any:
        for name in names:
            idx = cols.get(name)
            if idx is not None and idx < len(row):
                return row[idx]
        return default

    rows: list[dict] = []
    for row in props.get("rows") or []:
        raw_date = _cell(row, "UsageDate", "BillingMonth", "ChargePeriodStart", "Date", default="")
        date_str = str(raw_date or "")[:10]
        if len(date_str) == 8 and date_str.isdigit():
            date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        pretax = float(_cell(row, "PreTaxCost", "Cost", default=0) or 0)
        usd = float(_cell(row, "CostUSD", default=0) or 0)
        currency = str(_cell(row, "Currency", "BillingCurrency", default=default_currency) or default_currency)
        cost_usd = normalize_monthly_cost_usd({"pretax": pretax, "usd": usd, "currency": currency})
        idx = cost_column_indices(list(cols.keys()))
        row_names = list(cols.keys())
        service_name = service_name_from_cost_row(row, idx, names=row_names)
        rows.append({
            "date": date_str,
            "cost": pretax,
            "cost_usd": cost_usd if cost_usd is not None else 0.0,
            "currency": currency,
            "resource_group": str(_cell(row, "ResourceGroup", "ResourceGroupName", default="") or ""),
            "service_name": service_name,
            "resource_id": str(_cell(row, "ResourceId", default="") or ""),
            "resource_type": str(_cell(row, "ResourceType", default="") or ""),
        })
    return rows


def daily_subscription_rows_from_response(response: dict, *, default_currency: str = "CAD") -> list[dict]:
    """One row per day for subscription-level daily cost (no RG/service split)."""
    props = normalize_query_response(response).get("properties") or {}
    cols = _column_index(props.get("columns") or [])
    if not cols:
        return []

    def _cell(row: list, *names: str, default: Any = "") -> Any:
        for name in names:
            idx = cols.get(name)
            if idx is not None and idx < len(row):
                return row[idx]
        return default

    out: list[dict] = []
    for row in props.get("rows") or []:
        raw_date = _cell(row, "UsageDate", "BillingMonth", "ChargePeriodStart", "Date", default="")
        date_str = str(raw_date or "")[:10]
        if len(date_str) == 8 and date_str.isdigit():
            date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        if not date_str or len(date_str) < 10:
            continue
        pretax = float(_cell(row, "PreTaxCost", "Cost", default=0) or 0)
        usd = float(_cell(row, "CostUSD", default=0) or 0)
        currency = str(_cell(row, "Currency", "BillingCurrency", default=default_currency) or default_currency)
        cost_usd = normalize_monthly_cost_usd({"pretax": pretax, "usd": usd, "currency": currency})
        out.append({
            "date": date_str,
            "cost": pretax,
            "cost_usd": cost_usd if cost_usd is not None else 0.0,
            "currency": currency,
            "service_name": "__subscription__",
            "resource_group": "",
        })
    return out


def billing_currency_from_response(response: dict, default: str = "CAD") -> str:
    summary = summarize_cost_response(normalize_query_response(response))
    return summary.get("billing_currency") or default


class AzureCostClient:
    """Live Azure Cost Management queries using the same bearer token as ARM sync."""

    def __init__(self, db=None, token: str | None = None):
        self._db = db
        self._token = token

    def _query(self, scope: str, body: dict, *, throttle_label: str = "query") -> dict:
        log.info(
            "cost_client.query_start",
            scope=scope,
            timeframe=body.get("timeframe"),
            granularity=(body.get("dataset") or {}).get("granularity"),
            source=COST_API,
            phase=throttle_label,
        )
        result = _run_query(
            scope, body, db=self._db, token=self._token, throttle_label=throttle_label,
        )
        row_count = len((result.get("properties") or {}).get("rows") or [])
        log.info("cost_client.query_done", scope=scope, rows=row_count, source=COST_API)
        return result

    def query_cost(
        self,
        scope: str,
        timeframe: str = "MonthToDate",
        granularity: str = "Daily",
        group_by: list[dict] | None = None,
        filter_obj: dict | None = None,
    ) -> dict:
        if group_by is None and granularity == "Daily":
            group_by = [
                {"type": "Dimension", "name": "ResourceGroupName"},
                {"type": "Dimension", "name": "ServiceName"},
            ]
        body = _query_body(
            timeframe=timeframe,
            granularity=granularity,
            group_by=group_by,
            filter_obj=filter_obj,
        )
        return self._query(scope, body, throttle_label="daily")

    def query_cost_daily_subscription(
        self,
        subscription_id: str,
        timeframe: str = "MonthToDate",
        *,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict:
        """Subscription daily totals — one row per day (single API call, no RG/service split)."""
        scope = _normalize_scope("", subscription_id)
        body = _query_body(
            timeframe=timeframe,
            granularity="Daily",
            group_by=None,
            from_date=from_date,
            to_date=to_date,
        )
        result = self._query(scope, body, throttle_label="daily_subscription")
        result["billing_currency"] = billing_currency_from_response(result)
        return result

    def query_cost_by_resource(
        self,
        subscription_id: str,
        timeframe: str = "MonthToDate",
        *,
        resource_groups: list[str] | None = None,
    ) -> dict:
        scope = _normalize_scope("", subscription_id)
        group_by = [
            {"type": "Dimension", "name": "ResourceId"},
            {"type": "Dimension", "name": "ResourceType"},
            {"type": "Dimension", "name": "ResourceGroupName"},
            {"type": "Dimension", "name": "ServiceName"},
        ]
        rg_names = sorted({(rg or "").strip() for rg in (resource_groups or []) if (rg or "").strip()})
        if not rg_names:
            body = _query_body(timeframe=timeframe, granularity="None", group_by=group_by)
            return self._query(scope, body, throttle_label="by_resource")

        batch_size = cost_rg_batch_size()
        batches = [rg_names[i:i + batch_size] for i in range(0, len(rg_names), batch_size)]
        log.info(
            "cost_client.query_by_resource_batched",
            subscription_id=subscription_id,
            resource_groups=len(rg_names),
            batches=len(batches),
            batch_size=batch_size,
        )
        responses: list[dict] = []
        for idx, batch in enumerate(batches, start=1):
            body = _query_body(
                timeframe=timeframe,
                granularity="None",
                group_by=group_by,
                filter_obj=resource_group_filter(batch),
            )
            responses.append(
                self._query(scope, body, throttle_label=f"by_resource_batch_{idx}/{len(batches)}"),
            )
        merged = merge_query_responses(responses)
        row_count = len((merged.get("properties") or {}).get("rows") or [])
        log.info(
            "cost_client.query_by_resource_batched_done",
            subscription_id=subscription_id,
            rows=row_count,
            batches=len(batches),
        )
        return merged

    def query_cost_mtd_breakdown(
        self,
        subscription_id: str,
        timeframe: str = "MonthToDate",
    ) -> dict:
        """Single MTD query for service and resource-type charts (one API call)."""
        scope = _normalize_scope("", subscription_id)
        body = _query_body(
            timeframe=timeframe,
            granularity="None",
            group_by=[
                {"type": "Dimension", "name": "ServiceName"},
                {"type": "Dimension", "name": "ResourceType"},
            ],
        )
        result = self._query(scope, body, throttle_label="mtd_breakdown")
        result["billing_currency"] = billing_currency_from_response(result)
        return result

    def query_cost_mtd_by_resource_type(
        self,
        subscription_id: str,
        timeframe: str = "MonthToDate",
    ) -> dict:
        """Subscription-wide MTD totals grouped by ResourceType only (no per-resource rows)."""
        scope = _normalize_scope("", subscription_id)
        body = _query_body(
            timeframe=timeframe,
            granularity="None",
            group_by=[{"type": "Dimension", "name": "ResourceType"}],
        )
        result = self._query(scope, body, throttle_label="by_resource_type_mtd")
        result["billing_currency"] = billing_currency_from_response(result)
        return result

    def query_cost_by_service(
        self,
        subscription_id: str,
        timeframe: str = "MonthToDate",
        *,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict:
        scope = _normalize_scope("", subscription_id)
        body = _query_body(
            timeframe=timeframe,
            granularity="None",
            group_by=[
                {"type": "Dimension", "name": "ServiceName"},
                {"type": "Dimension", "name": "MeterCategory"},
            ],
            from_date=from_date,
            to_date=to_date,
        )
        result = self._query(scope, body, throttle_label="by_service")
        currency = billing_currency_from_response(result)
        result["billing_currency"] = currency
        return result

    def query_subscription_totals(
        self,
        subscription_id: str,
        timeframe: str = "MonthToDate",
        *,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict:
        scope = _normalize_scope("", subscription_id)
        body = _query_body(
            timeframe=timeframe,
            granularity="None",
            from_date=from_date,
            to_date=to_date,
        )
        result = self._query(scope, body)
        summary = summarize_cost_response(result)
        props = result.get("properties") or {}
        columns = props.get("columns") or [{"name": "PreTaxCost"}, {"name": "CostUSD"}, {"name": "Currency"}]
        currency = summary.get("billing_currency") or "CAD"
        result = {
            "properties": {
                "columns": columns,
                "rows": [[summary.get("pretax_total", 0), summary.get("cost_usd_total", 0), currency]],
            },
            "source": COST_API,
            **summary,
        }
        return result

    def query_forecast(self, subscription_id: str, timeframe: str = "MonthToDate") -> dict:
        scope_path = _normalize_scope("", subscription_id)
        url = f"{BASE}{scope_path}/providers/Microsoft.CostManagement/forecast"
        params = {"api-version": COST_API_VERSION}
        body = {
            "type": "ActualCost",
            "timeframe": timeframe,
            "dataset": {
                "granularity": "Daily",
                "aggregation": {"totalCost": {"name": "PreTaxCost", "function": "Sum"}},
            },
        }
        headers = _headers(self._db, self._token)
        try:
            data = _cost_request("POST", url, headers, params=params, payload=body)
            data["source"] = COST_API
            return normalize_query_response(data)
        except CostExportReadError as exc:
            log.warning("cost_client.query_forecast_failed", subscription_id=subscription_id, error=str(exc))
            return {"properties": {"columns": [], "rows": []}, "source": COST_API, "error": str(exc)}

    def list_budgets(self, subscription_id: str) -> list:
        scope_path = _normalize_scope("", subscription_id)
        url = f"{BASE}{scope_path}/providers/Microsoft.Consumption/budgets"
        params = {"api-version": "2024-08-01"}
        headers = _headers(self._db, self._token)
        try:
            from app.http_client import get_all_pages
            return get_all_pages(url, headers, params=params, use_cache=False)
        except AzureAPIError as exc:
            log.warning("cost_client.list_budgets_failed", subscription_id=subscription_id, error=str(exc))
            return []

    def list_dimensions(self, subscription_id: str) -> list:
        scope_path = _normalize_scope("", subscription_id)
        url = f"{BASE}{scope_path}/providers/Microsoft.CostManagement/dimensions"
        params = {"api-version": COST_API_VERSION, "$top": "1000"}
        headers = _headers(self._db, self._token)
        try:
            from app.http_client import get_all_pages
            return get_all_pages(url, headers, params=params, use_cache=False)
        except AzureAPIError as exc:
            log.warning("cost_client.list_dimensions_failed", subscription_id=subscription_id, error=str(exc))
            return []


__all__ = [
    "AzureCostClient",
    "COST_API",
    "COST_API_VERSION",
    "CostExportNotConfiguredError",
    "CostExportReadError",
    "billing_currency_from_response",
    "cost_page_delay_sec",
    "cost_query_delay_sec",
    "cost_resource_type_batch_size",
    "cost_rg_batch_size",
    "daily_query_to_export_rows",
    "daily_subscription_rows_from_response",
    "merge_query_responses",
    "normalize_query_response",
    "resource_group_filter",
    "resource_type_filter",
]
