"""Read Azure cost data from a Cost Management **FOCUS** export in blob storage (legacy).

Primary cost ingestion uses the Azure Cost Management API via ``app.azure_cost`` and
the cached ARM bearer token. This module remains for optional FOCUS blob export use.

Parses the FOCUS cost and usage details file schema (v1.0+):
https://learn.microsoft.com/en-us/azure/cost-management-billing/dataset-schema/cost-usage-details-focus

Configuration (App Settings) — auth (first match wins):
  Option B — account key (recommended when set explicitly):
    COST_EXPORT_ACCOUNT_NAME        Storage account name
    COST_EXPORT_ACCOUNT_KEY         Storage account key (mark as secret in App Service)
    COST_EXPORT_BLOB_ENDPOINT       Optional blob endpoint host (default: {name}.blob.core.windows.net)

  Option A — connection string:
    COST_EXPORT_CONNECTION_STRING   Dedicated cost-export connection string

  Optional fallbacks:
    AZURE_STORAGE_CONNECTION_STRING / STORAGECONNSTR_* / CUSTOMCONNSTR_*
    COST_EXPORT_SAS_URL             Container or account SAS URL
    COST_EXPORT_BLOB_SAS_URL        Single-file SAS URL

  COST_EXPORT_CONTAINER           Default ``cost``
  COST_EXPORT_PREFIX              Default ``cost/costfordahboard-actual-cost``
  COST_EXPORT_CACHE_TTL_SEC       Parsed-export cache TTL (default: 1800)
"""
from __future__ import annotations

import csv
import gc
import gzip
import io
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import IO, Callable, Iterator

import structlog

from app.focus_mapping import (
    PICK_BILLED_COST,
    PICK_BILLED_USD,
    PICK_BILLING_CURRENCY,
    PICK_RESOURCE_GROUP,
    PICK_RESOURCE_ID,
    PICK_RESOURCE_TYPE,
    PICK_SERVICE_NAME,
    PICK_SUBSCRIPTION,
    PICK_USAGE_DATE,
    normalize_arm_id,
    normalize_usage_date,
)

log = structlog.get_logger()

_DEFAULT_EXPORT_PREFIX = "cost/costfordahboard-actual-cost"

_CACHE_TTL = float(os.getenv("COST_EXPORT_CACHE_TTL_SEC", "1800"))
_MAX_CACHE_ROWS = int(os.getenv("COST_EXPORT_MAX_CACHE_ROWS", "25000"))
_lock = threading.Lock()
_cache: dict = {}  # subscription_id -> (expires, rows)


class CostExportNotConfiguredError(RuntimeError):
    """Raised when cost export blob storage credentials are missing."""


class CostExportReadError(RuntimeError):
    """Raised when the blob export cannot be listed, downloaded, or parsed."""


@dataclass
class ParsedCostExport:
    """Streaming parse result — aggregates only, no full row list in memory."""
    blob_rows: int = 0
    parsed_rows: int = 0
    skipped_subscription: int = 0
    skipped_no_date: int = 0
    focus_schema: bool = False
    legacy_actual_schema: bool = False
    services_by_month: dict[str, dict[str, dict]] = field(default_factory=dict)
    resources_by_month: dict[str, dict[str, dict]] = field(default_factory=dict)
    daily_by_rg: dict[tuple[str, str], dict] = field(default_factory=dict)
    daily_by_service: dict[tuple[str, str], dict] = field(default_factory=dict)
    months_seen: set[str] = field(default_factory=set)
    rows_by_month: dict[str, int] = field(default_factory=dict)


def _connection_string() -> str | None:
    """Resolve storage connection string from env or App Service connection strings."""
    for key in (
        "COST_EXPORT_CONNECTION_STRING",
        "AZURE_STORAGE_CONNECTION_STRING",
        "AZURE_STORAGE_CONNECTION",
    ):
        val = (os.getenv(key) or "").strip()
        if val:
            return val
    for env_key, value in os.environ.items():
        if not value:
            continue
        upper = env_key.upper()
        if upper.startswith("STORAGECONNSTR_"):
            return value.strip()
        if upper.startswith("CUSTOMCONNSTR_") and "cost" in upper:
            return value.strip()
    return None


def _account_credentials() -> tuple[str, str] | None:
    name = (
        os.getenv("COST_EXPORT_ACCOUNT_NAME")
        or os.getenv("AZURE_STORAGE_ACCOUNT")
        or ""
    ).strip()
    key = (
        os.getenv("COST_EXPORT_ACCOUNT_KEY")
        or os.getenv("AZURE_STORAGE_KEY")
        or ""
    ).strip()
    if name and key:
        return name, key
    return None


def _account_blob_endpoint(account_name: str) -> str:
    custom = (os.getenv("COST_EXPORT_BLOB_ENDPOINT") or "").strip().rstrip("/")
    if custom:
        if custom.startswith("https://"):
            return custom
        return f"https://{custom}"
    return f"https://{account_name}.blob.core.windows.net"


def _explicit_account_key_configured() -> bool:
    return bool(
        (os.getenv("COST_EXPORT_ACCOUNT_NAME") or "").strip()
        and (os.getenv("COST_EXPORT_ACCOUNT_KEY") or "").strip()
    )


def _auth_method() -> str | None:
    # Option B: explicit COST_EXPORT_ACCOUNT_* takes priority over SAS / shared storage env vars.
    if _explicit_account_key_configured():
        return "account_key"
    if _connection_string():
        return "connection_string"
    if _account_credentials():
        return "account_key"
    if os.getenv("COST_EXPORT_BLOB_SAS_URL"):
        return "blob_sas_url"
    if os.getenv("COST_EXPORT_SAS_URL"):
        return "sas_url"
    return None


def export_config_summary() -> dict:
    """Non-secret configuration summary for logs."""
    auth = _auth_method()
    account_name = None
    creds = _account_credentials()
    if creds:
        account_name = creds[0]
    endpoint = None
    if account_name:
        endpoint = _account_blob_endpoint(account_name).replace("https://", "")
    return {
        "configured": is_configured(),
        "auth_method": auth,
        "container": os.getenv("COST_EXPORT_CONTAINER", "cost"),
        "prefix": _export_prefix(),
        "cache_ttl_sec": _CACHE_TTL,
        "account_name": account_name,
        "blob_endpoint": endpoint,
        "has_connection_string": bool(_connection_string()),
    }


def is_configured() -> bool:
    return _auth_method() is not None


def _warn_sas_list_permission(sas_url: str) -> None:
    """Log when a container/account SAS is missing List (l) permission."""
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(sas_url).query)
    sp = (qs.get("sp") or [""])[0].lower()
    if sp and "l" not in sp:
        log.warning(
            "cost_export.sas_missing_list_permission",
            sp=sp,
            hint="Regenerate SAS with Read + List (sp must include r and l). "
                 "Or set COST_EXPORT_BLOB_SAS_URL to a single export file SAS.",
        )


def _storage_error_message(exc: Exception) -> str:
    """Turn Azure SDK errors into actionable messages (no secrets)."""
    err_text = str(exc)
    if "AuthorizationFailure" in err_text:
        return (
            "Blob storage authorization failed when listing or reading the cost export. "
            "Check COST_EXPORT_ACCOUNT_NAME, COST_EXPORT_ACCOUNT_KEY, COST_EXPORT_CONTAINER, "
            "and COST_EXPORT_PREFIX. If the storage account has a firewall, allow App Service "
            f"outbound IPs. Configured prefix: '{_export_prefix()}'."
        )
    if "AuthenticationFailed" in err_text:
        return (
            "Blob storage authentication failed. Verify COST_EXPORT_ACCOUNT_NAME and "
            "COST_EXPORT_ACCOUNT_KEY in application settings."
        )
    return f"Cost export read failed: {exc}"


def _classify_storage_error(exc: Exception) -> CostExportReadError:
    return CostExportReadError(_storage_error_message(exc))


def ensure_configured() -> None:
    if not is_configured():
        log.error(
            "cost_export.not_configured",
            hint="Set COST_EXPORT_ACCOUNT_NAME and COST_EXPORT_ACCOUNT_KEY (Option B)",
            config=export_config_summary(),
        )
        raise CostExportNotConfiguredError(
            "Cost export blob is not configured. Set COST_EXPORT_ACCOUNT_NAME and "
            "COST_EXPORT_ACCOUNT_KEY in application settings."
        )


def _blob_service_client():
    """Create BlobServiceClient from the active auth method."""
    auth = _auth_method()

    if auth == "account_key":
        creds = _account_credentials()
        if not creds:
            return None
        from azure.storage.blob import BlobServiceClient

        account_name, account_key = creds
        account_url = _account_blob_endpoint(account_name)
        return BlobServiceClient(account_url=account_url, credential=account_key)

    if auth == "connection_string":
        conn = _connection_string()
        if not conn:
            return None
        from azure.storage.blob import BlobServiceClient

        return BlobServiceClient.from_connection_string(conn)

    if auth == "sas_url":
        from urllib.parse import urlparse
        from azure.storage.blob import BlobServiceClient, ContainerClient

        sas_url = (os.getenv("COST_EXPORT_SAS_URL") or "").strip()
        if not sas_url:
            return None
        _warn_sas_list_permission(sas_url)
        path = urlparse(sas_url).path.strip("/")
        if path:
            return ContainerClient.from_container_url(sas_url)
        return BlobServiceClient(account_url=sas_url)

    return None


def _container_client():
    container = os.getenv("COST_EXPORT_CONTAINER", "cost")
    auth = _auth_method()
    client = _blob_service_client()
    if client is None:
        return None

    from azure.storage.blob import ContainerClient

    if isinstance(client, ContainerClient):
        log.info(
            "cost_export.container_client",
            auth_method=auth,
            container=container,
            path_in_url=True,
        )
        return client

    log.info(
        "cost_export.container_client",
        auth_method=auth,
        container=container,
        path_in_url=False,
    )
    return client.get_container_client(container)


def _pick(row: dict, candidates: list[str]) -> str:
    for c in candidates:
        if c in row and row[c] not in (None, ""):
            return row[c]
    lower = {k.lower(): v for k, v in row.items()}
    for c in candidates:
        v = lower.get(c.lower())
        if v not in (None, "", None):
            return v
    return ""


def _to_float(value: str) -> float:
    try:
        return float(str(value).replace(",", "").strip() or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_subscription_id(value: str) -> str:
    v = (value or "").strip().lower()
    if "/subscriptions/" in v:
        return v.split("/subscriptions/", 1)[1].split("/")[0]
    return v


def _subscription_from_row(raw: dict) -> str:
    sub = _normalize_subscription_id(_pick(raw, PICK_SUBSCRIPTION))
    if sub:
        return sub
    rid = (_pick(raw, PICK_RESOURCE_ID) or "").lower()
    if "/subscriptions/" in rid:
        return rid.split("/subscriptions/", 1)[1].split("/")[0]
    return ""


def _resource_group_from_id(resource_id: str) -> str:
    rid = (resource_id or "").lower()
    if "/resourcegroups/" in rid:
        return rid.split("/resourcegroups/", 1)[1].split("/")[0]
    return ""


def _usage_date(raw: dict) -> str:
    return normalize_usage_date(_pick(raw, PICK_USAGE_DATE))


def _normalize_row(raw: dict) -> dict:
    """Map one CSV row to internal normalized fields (FOCUS-accurate)."""
    resource_id = normalize_arm_id(_pick(raw, PICK_RESOURCE_ID) or "")
    resource_group = _pick(raw, PICK_RESOURCE_GROUP) or _resource_group_from_id(resource_id)
    billed = _to_float(_pick(raw, PICK_BILLED_COST))
    usd = _to_float(_pick(raw, PICK_BILLED_USD))
    currency = _pick(raw, PICK_BILLING_CURRENCY) or "USD"
    service_name = _pick(raw, PICK_SERVICE_NAME) or "Other"
    return {
        "resource_id": resource_id,
        "resource_group": resource_group,
        "service_name": service_name,
        "resource_type": _pick(raw, PICK_RESOURCE_TYPE),
        "date": _usage_date(raw),
        "cost": billed,
        "cost_usd": usd,
        "currency": currency,
    }


def _export_prefix() -> str:
    raw = os.getenv("COST_EXPORT_PREFIX")
    if raw is None:
        return _DEFAULT_EXPORT_PREFIX
    raw = raw.strip()
    return raw if raw else ""


def _is_cost_data_blob(name: str) -> bool:
    lower = name.lower()
    return lower.endswith(".csv") or lower.endswith(".csv.gz")


def _blob_directory(blob_name: str) -> str:
    if "/" not in blob_name:
        return ""
    return blob_name.rsplit("/", 1)[0] + "/"


def _latest_export_parts(container_client, prefix: str) -> list[str]:
    name_filter = prefix or ""
    log.info("cost_export.list_blobs_start", prefix=name_filter or "(container root)")
    scanned = 0
    data_blobs = 0
    latest_name = None
    latest_mtime = None
    for blob in container_client.list_blobs(name_starts_with=name_filter):
        scanned += 1
        if not _is_cost_data_blob(blob.name):
            continue
        data_blobs += 1
        mtime = getattr(blob, "last_modified", None)
        if latest_mtime is None or (mtime and mtime > latest_mtime):
            latest_mtime, latest_name = mtime, blob.name

    log.info(
        "cost_export.list_blobs_done",
        prefix=name_filter or "(container root)",
        blobs_scanned=scanned,
        data_blobs_found=data_blobs,
        latest_blob=latest_name,
        latest_mtime=str(latest_mtime) if latest_mtime else None,
    )

    if not latest_name:
        return []

    export_dir = _blob_directory(latest_name)
    if not export_dir:
        log.info("cost_export.single_part_export", blob=latest_name)
        return [latest_name]

    parts = [
        blob.name
        for blob in container_client.list_blobs(name_starts_with=export_dir)
        if _is_cost_data_blob(blob.name)
    ]
    parts = sorted(parts)
    log.info(
        "cost_export.export_run_parts",
        export_dir=export_dir,
        part_count=len(parts),
        parts=parts,
    )
    return parts


def _decode_export_blob(raw: bytes, blob_name: str) -> str:
    if blob_name.lower().endswith(".gz"):
        raw = gzip.decompress(raw)
    return raw.decode("utf-8-sig", errors="replace")


def _open_csv_text_stream(raw: bytes, blob_name: str) -> IO[str]:
    """Open a text stream for CSV parsing without materializing the full decompressed string."""
    bio = io.BytesIO(raw)
    if blob_name.lower().endswith(".gz"):
        gz = gzip.GzipFile(fileobj=bio)
        return io.TextIOWrapper(gz, encoding="utf-8-sig", errors="replace", newline="")
    return io.TextIOWrapper(bio, encoding="utf-8-sig", errors="replace", newline="")


def _month_key(date_str: str) -> str:
    return (date_str or "")[:7]


def _accumulate_service(
    services_by_month: dict[str, dict[str, dict]],
    month: str,
    service_name: str,
    pretax: float,
    usd: float,
    currency: str,
) -> None:
    bucket = services_by_month.setdefault(month, {})
    svc = service_name or "Other"
    entry = bucket.setdefault(
        svc,
        {"pretax": 0.0, "usd": 0.0, "currency": currency or "USD"},
    )
    entry["pretax"] += pretax
    entry["usd"] += usd
    if currency:
        entry["currency"] = currency


def _accumulate_resource(
    resources_by_month: dict[str, dict[str, dict]],
    month: str,
    row: dict,
) -> None:
    rid = normalize_arm_id(row.get("resource_id") or "")
    if not rid:
        return
    bucket = resources_by_month.setdefault(month, {})
    entry = bucket.setdefault(
        rid,
        {
            "pretax": 0.0,
            "usd": 0.0,
            "currency": row.get("currency") or "USD",
            "resource_type": row.get("resource_type") or "",
            "resource_group": row.get("resource_group") or "",
            "service_name": row.get("service_name") or "Other",
        },
    )
    entry["pretax"] += float(row.get("cost") or 0.0)
    entry["usd"] += float(row.get("cost_usd") or 0.0)
    if row.get("currency"):
        entry["currency"] = row["currency"]
    if row.get("resource_type"):
        entry["resource_type"] = row["resource_type"]
    if row.get("resource_group"):
        entry["resource_group"] = row["resource_group"]
    if row.get("service_name"):
        entry["service_name"] = row["service_name"]


def _accumulate_daily(parsed: ParsedCostExport, row: dict) -> None:
    cost_date = (row.get("date") or "").strip()[:10]
    if not cost_date:
        return
    currency = row.get("currency") or "USD"
    pretax = float(row.get("cost") or 0.0)
    usd = float(row.get("cost_usd") or pretax)

    rg_key = (cost_date, row.get("resource_group") or "")
    rg_bucket = parsed.daily_by_rg.setdefault(
        rg_key,
        {"pretax": 0.0, "usd": 0.0, "currency": currency},
    )
    rg_bucket["pretax"] += pretax
    rg_bucket["usd"] += usd
    if currency:
        rg_bucket["currency"] = currency

    svc_name = row.get("service_name") or "Other"
    svc_key = (cost_date, svc_name)
    svc_bucket = parsed.daily_by_service.setdefault(
        svc_key,
        {"pretax": 0.0, "usd": 0.0, "currency": currency},
    )
    svc_bucket["pretax"] += pretax
    svc_bucket["usd"] += usd
    if currency:
        svc_bucket["currency"] = currency


def _ingest_normalized_row(parsed: ParsedCostExport, row: dict) -> None:
    month = _month_key(row.get("date") or "")
    if len(month) != 7:
        return
    parsed.months_seen.add(month)
    parsed.rows_by_month[month] = parsed.rows_by_month.get(month, 0) + 1
    parsed.parsed_rows += 1
    _accumulate_service(
        parsed.services_by_month,
        month,
        row.get("service_name") or "Other",
        float(row.get("cost") or 0.0),
        float(row.get("cost_usd") or 0.0),
        row.get("currency") or "USD",
    )
    _accumulate_resource(parsed.resources_by_month, month, row)
    _accumulate_daily(parsed, row)


def _parse_csv_stream(
    stream: IO[str],
    subscription_id: str,
    *,
    collect_rows: bool = False,
    row_filter: Callable[[dict], bool] | None = None,
    parsed: ParsedCostExport | None = None,
) -> tuple[list[dict], dict]:
    reader = csv.DictReader(stream)
    fields = reader.fieldnames or []
    lower_fields = {(f or "").lower() for f in fields}
    is_focus = "billedcost" in lower_fields
    is_legacy_actual = "costinbillingcurrency" in lower_fields
    if parsed is not None:
        parsed.focus_schema = parsed.focus_schema or is_focus
        parsed.legacy_actual_schema = parsed.legacy_actual_schema or is_legacy_actual
    log.info(
        "cost_export.parse_csv_start",
        subscription_id=subscription_id,
        focus_schema=is_focus,
        legacy_actual_schema=is_legacy_actual,
        column_count=len(fields),
        columns=fields[:20],
    )

    sub_filter = _normalize_subscription_id(subscription_id)
    rows: list[dict] = []
    skipped_subscription = 0
    skipped_no_date = 0
    for raw in reader:
        if parsed is not None:
            parsed.blob_rows += 1
        row_sub = _subscription_from_row(raw)
        if sub_filter and row_sub and row_sub != sub_filter:
            skipped_subscription += 1
            if parsed is not None:
                parsed.skipped_subscription += 1
            continue
        normalized = _normalize_row(raw)
        if not normalized["date"]:
            skipped_no_date += 1
            if parsed is not None:
                parsed.skipped_no_date += 1
            continue
        if parsed is not None:
            _ingest_normalized_row(parsed, normalized)
        if collect_rows and (row_filter is None or row_filter(normalized)):
            rows.append(normalized)

    stats = {
        "parsed_rows": parsed.parsed_rows if parsed is not None else len(rows),
        "skipped_subscription": skipped_subscription,
        "skipped_no_date": skipped_no_date,
        "focus_schema": is_focus,
        "legacy_actual_schema": is_legacy_actual,
    }
    log.info("cost_export.parse_csv_done", subscription_id=subscription_id, **stats)
    return rows, stats


def _parse_csv_text(text: str, subscription_id: str) -> tuple[list[dict], dict]:
    return _parse_csv_stream(io.StringIO(text), subscription_id, collect_rows=True)


def _download_blob_sas_url(subscription_id: str, blob_sas_url: str) -> list[dict]:
    """Read one export file when only a blob-level SAS is available (no list permission)."""
    from urllib.parse import urlparse
    from azure.storage.blob import BlobClient

    blob_sas_url = blob_sas_url.strip()
    log.info(
        "cost_export.single_blob_download",
        host=urlparse(blob_sas_url).netloc,
        path=urlparse(blob_sas_url).path,
    )
    raw = BlobClient.from_blob_url(blob_sas_url).download_blob().readall()
    blob_name = urlparse(blob_sas_url).path.rsplit("/", 1)[-1] or "export.csv.gz"
    with _open_csv_text_stream(raw, blob_name) as stream:
        rows, stats = _parse_csv_stream(stream, subscription_id, collect_rows=True)
    del raw
    log.info("cost_export.single_blob_done", subscription_id=subscription_id, **stats)
    return rows


def _download_parsed_export(subscription_id: str) -> ParsedCostExport:
    """Stream-download export blobs and aggregate in one pass (sync path)."""
    ensure_configured()
    if _auth_method() == "blob_sas_url":
        blob_sas = (os.getenv("COST_EXPORT_BLOB_SAS_URL") or "").strip()
        if blob_sas:
            rows = _download_blob_sas_url(subscription_id, blob_sas)
            parsed = ParsedCostExport(blob_rows=len(rows), parsed_rows=len(rows))
            for row in rows:
                _ingest_normalized_row(parsed, row)
            del rows
            return parsed

    prefix = _export_prefix()
    container_client = _container_client()
    if container_client is None:
        raise CostExportReadError("Failed to create blob container client")

    part_blobs = _latest_export_parts(container_client, prefix)
    if not part_blobs:
        log.error("cost_export.no_data_blobs", prefix=prefix, config=export_config_summary())
        raise CostExportReadError(
            f"No cost export CSV/GZ blobs found under prefix '{prefix or '(root)'}'"
        )

    parsed = ParsedCostExport()
    total_bytes = 0
    for blob_name in part_blobs:
        t0 = time.monotonic()
        raw = container_client.download_blob(blob_name).readall()
        total_bytes += len(raw)
        with _open_csv_text_stream(raw, blob_name) as stream:
            _part_rows, stats = _parse_csv_stream(stream, subscription_id, parsed=parsed)
        del raw
        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        log.info(
            "cost_export.part_downloaded",
            blob=blob_name,
            compressed_bytes=total_bytes,
            elapsed_ms=elapsed_ms,
            **stats,
        )
        gc.collect()

    log.info(
        "cost_export.download_complete",
        subscription_id=subscription_id,
        prefix=prefix,
        parts=len(part_blobs),
        total_compressed_bytes=total_bytes,
        row_count=parsed.parsed_rows,
        blob_rows=parsed.blob_rows,
        unique_services=sum(len(v) for v in parsed.services_by_month.values()),
        unique_resources=sum(len(v) for v in parsed.resources_by_month.values()),
        months=sorted(parsed.months_seen),
    )
    return parsed


def _download_and_parse(subscription_id: str) -> list[dict]:
    ensure_configured()
    if _auth_method() == "blob_sas_url":
        blob_sas = (os.getenv("COST_EXPORT_BLOB_SAS_URL") or "").strip()
        if blob_sas:
            return _download_blob_sas_url(subscription_id, blob_sas)

    prefix = _export_prefix()
    container_client = _container_client()
    if container_client is None:
        raise CostExportReadError("Failed to create blob container client")

    part_blobs = _latest_export_parts(container_client, prefix)
    if not part_blobs:
        log.error("cost_export.no_data_blobs", prefix=prefix, config=export_config_summary())
        raise CostExportReadError(
            f"No cost export CSV/GZ blobs found under prefix '{prefix or '(root)'}'"
        )

    all_rows: list[dict] = []
    total_bytes = 0
    for blob_name in part_blobs:
        t0 = time.monotonic()
        raw = container_client.download_blob(blob_name).readall()
        total_bytes += len(raw)
        with _open_csv_text_stream(raw, blob_name) as stream:
            part_rows, stats = _parse_csv_stream(stream, subscription_id, collect_rows=True)
        del raw
        all_rows.extend(part_rows)
        elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
        log.info(
            "cost_export.part_downloaded",
            blob=blob_name,
            compressed_bytes=total_bytes,
            parsed_rows=len(part_rows),
            elapsed_ms=elapsed_ms,
            **stats,
        )
        del part_rows
        gc.collect()

    pretax_total = round(sum(r["cost"] for r in all_rows), 2)
    usd_total = round(sum(r["cost_usd"] for r in all_rows), 2)
    services = len({r["service_name"] for r in all_rows})
    resources = len({r["resource_id"] for r in all_rows if r["resource_id"]})
    dates = sorted({r["date"] for r in all_rows if r["date"]})
    log.info(
        "cost_export.download_complete",
        subscription_id=subscription_id,
        prefix=prefix,
        parts=len(part_blobs),
        total_compressed_bytes=total_bytes,
        row_count=len(all_rows),
        unique_services=services,
        unique_resources=resources,
        date_range=f"{dates[0]}..{dates[-1]}" if dates else None,
        pretax_total=pretax_total,
        usd_total=usd_total,
        billing_currency=_billing_currency(all_rows),
    )
    return all_rows


def load_rows(subscription_id: str, timeframe: str = "MonthToDate") -> list[dict]:
    """Return normalized export rows for a subscription (blob only, cached briefly)."""
    subscription_id = _normalize_subscription_id(subscription_id)
    ensure_configured()
    cache_key = f"{subscription_id}:{timeframe}"
    now = time.monotonic()
    with _lock:
        hit = _cache.get(cache_key)
        if hit and hit[0] > now:
            log.info(
                "cost_export.cache_hit",
                subscription_id=subscription_id,
                timeframe=timeframe,
                row_count=len(hit[1]),
                ttl_remaining_sec=round(hit[0] - now, 1),
            )
            return hit[1]

    log.info(
        "cost_export.cache_miss",
        subscription_id=subscription_id,
        timeframe=timeframe,
        config=export_config_summary(),
    )
    try:
        rows = _download_rows_filtered(subscription_id, timeframe)
    except (CostExportNotConfiguredError, CostExportReadError):
        raise
    except Exception as exc:
        msg = _storage_error_message(exc)
        if "AuthorizationFailure" in str(exc) or "AuthenticationFailed" in str(exc):
            log.warning(
                "cost_export.read_failed",
                subscription_id=subscription_id,
                error=msg,
                config=export_config_summary(),
            )
        else:
            log.exception(
                "cost_export.read_failed",
                subscription_id=subscription_id,
                error=msg,
                config=export_config_summary(),
            )
        raise _classify_storage_error(exc) from exc

    if len(rows) <= _MAX_CACHE_ROWS:
        with _lock:
            _cache[cache_key] = (now + _CACHE_TTL, rows)
    else:
        log.warning(
            "cost_export.cache_skipped",
            subscription_id=subscription_id,
            row_count=len(rows),
            max_cache_rows=_MAX_CACHE_ROWS,
        )
    return rows


def clear_cache() -> None:
    with _lock:
        cleared = len(_cache)
        _cache.clear()
    log.info("cost_export.cache_cleared", entries_cleared=cleared)


def filter_rows_by_timeframe(rows: list[dict], timeframe: str) -> list[dict]:
    """Filter export rows to match Cost Management timeframe semantics."""
    if not rows:
        return rows
    today = date.today()
    if timeframe in ("MonthToDate", "BillingMonthToDate"):
        start = today.replace(day=1)
        end = today
    elif timeframe == "TheLastMonth":
        first_this = today.replace(day=1)
        end = first_this - timedelta(days=1)
        start = end.replace(day=1)
    else:
        log.warning("cost_export.unknown_timeframe", timeframe=timeframe, action="return_all_rows")
        return rows

    filtered: list[dict] = []
    for row in rows:
        raw_date = (row.get("date") or "")[:10]
        if len(raw_date) < 10:
            continue
        try:
            row_date = date.fromisoformat(raw_date)
        except ValueError:
            continue
        if start <= row_date <= end:
            filtered.append(row)

    log.info(
        "cost_export.timeframe_filter",
        timeframe=timeframe,
        start=str(start),
        end=str(end),
        input_rows=len(rows),
        output_rows=len(filtered),
    )
    return filtered


def filter_rows_by_month(rows: list[dict], month: str) -> list[dict]:
    """Keep rows whose usage date falls in YYYY-MM."""
    prefix = (month or "")[:7]
    if not prefix:
        return rows
    filtered = [r for r in rows if (r.get("date") or "").startswith(prefix)]
    log.info(
        "cost_export.month_filter",
        month=prefix,
        input_rows=len(rows),
        output_rows=len(filtered),
    )
    return filtered


def latest_month_in_rows(rows: list[dict]) -> str | None:
    """Return YYYY-MM of the newest usage date in normalized rows."""
    latest: str | None = None
    for row in rows:
        d = (row.get("date") or "")[:7]
        if len(d) == 7 and d[4] == "-" and (latest is None or d > latest):
            latest = d
    return latest


def resolve_mtd_rows(rows: list[dict]) -> tuple[list[dict], str, str, str]:
    """
    Rows and month key (YYYY-MM) for MTD persistence (1st of month through today).

    Returns (rows, month, mtd_start, mtd_end) as YYYY-MM-DD strings.
    When the export has no current-month rows yet, falls back to the latest month.
    """
    today = date.today()
    today_month = today.strftime("%Y-%m")
    mtd_start = today.replace(day=1).isoformat()
    mtd_end = today.isoformat()

    mtd = filter_rows_by_timeframe(rows, "MonthToDate")
    if mtd:
        return mtd, today_month, mtd_start, mtd_end

    fallback_month = latest_month_in_rows(rows)
    if fallback_month:
        mtd = filter_rows_by_month(rows, fallback_month)
        if mtd:
            dates = sorted(r.get("date") or "" for r in mtd if r.get("date"))
            fb_start = f"{fallback_month}-01"
            fb_end = dates[-1] if dates else fb_start
            log.warning(
                "cost_export.mtd_fallback_latest_month",
                requested_month=today_month,
                fallback_month=fallback_month,
                row_count=len(mtd),
                mtd_start=fb_start,
                mtd_end=fb_end,
            )
            return mtd, fallback_month, fb_start, fb_end

    log.warning(
        "cost_export.mtd_empty",
        requested_month=today_month,
        input_rows=len(rows),
    )
    return [], today_month, mtd_start, mtd_end


def _timeframe_bounds(timeframe: str) -> tuple[date, date] | None:
    today = date.today()
    if timeframe in ("MonthToDate", "BillingMonthToDate"):
        return today.replace(day=1), today
    if timeframe == "TheLastMonth":
        first_this = today.replace(day=1)
        end = first_this - timedelta(days=1)
        return end.replace(day=1), end
    return None


def _row_in_timeframe(row: dict, start: date, end: date) -> bool:
    raw_date = (row.get("date") or "")[:10]
    if len(raw_date) < 10:
        return False
    try:
        row_date = date.fromisoformat(raw_date)
    except ValueError:
        return False
    return start <= row_date <= end


def resolve_parsed_mtd(
    parsed: ParsedCostExport,
) -> tuple[str, str, str, dict[str, dict], dict[str, dict], int]:
    """
    Pick MTD month from aggregated export data.

    Returns (month, mtd_start, mtd_end, services_by_name, resources_by_id, mtd_row_count).
    """
    today = date.today()
    month = today.strftime("%Y-%m")
    mtd_start = today.replace(day=1).isoformat()
    mtd_end = today.isoformat()

    services = parsed.services_by_month.get(month, {})
    resources = parsed.resources_by_month.get(month, {})
    mtd_rows = parsed.rows_by_month.get(month, 0)
    if services or resources:
        return month, mtd_start, mtd_end, services, resources, mtd_rows

    if parsed.months_seen:
        fallback_month = max(parsed.months_seen)
        services = parsed.services_by_month.get(fallback_month, {})
        resources = parsed.resources_by_month.get(fallback_month, {})
        mtd_rows = parsed.rows_by_month.get(fallback_month, 0)
        fb_start = f"{fallback_month}-01"
        fb_end = fb_start
        log.warning(
            "cost_export.mtd_fallback_latest_month",
            requested_month=month,
            fallback_month=fallback_month,
            row_count=mtd_rows,
            mtd_start=fb_start,
            mtd_end=fb_end,
        )
        return fallback_month, fb_start, fb_end, services, resources, mtd_rows

    log.warning(
        "cost_export.mtd_empty",
        requested_month=month,
        blob_rows=parsed.blob_rows,
    )
    return month, mtd_start, mtd_end, {}, {}, 0


def load_parsed_export(subscription_id: str) -> ParsedCostExport:
    """Stream-parse export blobs into aggregates (for sync — avoids holding all rows)."""
    subscription_id = _normalize_subscription_id(subscription_id)
    ensure_configured()
    log.info(
        "cost_export.parsed_export_start",
        subscription_id=subscription_id,
        config=export_config_summary(),
    )
    try:
        parsed = _download_parsed_export(subscription_id)
    except (CostExportNotConfiguredError, CostExportReadError):
        raise
    except Exception as exc:
        raise _classify_storage_error(exc) from exc
    log.info(
        "cost_export.parsed_export_done",
        subscription_id=subscription_id,
        parsed_rows=parsed.parsed_rows,
        blob_rows=parsed.blob_rows,
    )
    return parsed


def _download_rows_filtered(subscription_id: str, timeframe: str) -> list[dict]:
    """Stream-parse blobs and retain only rows in the requested timeframe."""
    bounds = _timeframe_bounds(timeframe)
    if bounds is None:
        return _download_and_parse(subscription_id)

    start, end = bounds
    row_filter = lambda row: _row_in_timeframe(row, start, end)

    ensure_configured()
    if _auth_method() == "blob_sas_url":
        blob_sas = (os.getenv("COST_EXPORT_BLOB_SAS_URL") or "").strip()
        if blob_sas:
            all_rows = _download_blob_sas_url(subscription_id, blob_sas)
            return [r for r in all_rows if row_filter(r)]

    prefix = _export_prefix()
    container_client = _container_client()
    if container_client is None:
        raise CostExportReadError("Failed to create blob container client")

    part_blobs = _latest_export_parts(container_client, prefix)
    if not part_blobs:
        raise CostExportReadError(
            f"No cost export CSV/GZ blobs found under prefix '{prefix or '(root)'}'"
        )

    rows: list[dict] = []
    for blob_name in part_blobs:
        raw = container_client.download_blob(blob_name).readall()
        with _open_csv_text_stream(raw, blob_name) as stream:
            part_rows, _stats = _parse_csv_stream(
                stream,
                subscription_id,
                collect_rows=True,
                row_filter=row_filter,
            )
        del raw
        rows.extend(part_rows)
        del part_rows
        gc.collect()

    if not rows and timeframe in ("MonthToDate", "BillingMonthToDate"):
        parsed = _download_parsed_export(subscription_id)
        month, mtd_start, mtd_end, _services, _resources, _mtd_rows = resolve_parsed_mtd(parsed)
        if month:
            fb_start = date.fromisoformat(mtd_start)
            fb_end = date.fromisoformat(mtd_end)
            return _download_rows_filtered_with_bounds(subscription_id, fb_start, fb_end)
    return rows


def _download_rows_filtered_with_bounds(
    subscription_id: str,
    start: date,
    end: date,
) -> list[dict]:
    row_filter = lambda row: _row_in_timeframe(row, start, end)
    prefix = _export_prefix()
    container_client = _container_client()
    if container_client is None:
        raise CostExportReadError("Failed to create blob container client")
    part_blobs = _latest_export_parts(container_client, prefix)
    rows: list[dict] = []
    for blob_name in part_blobs:
        raw = container_client.download_blob(blob_name).readall()
        with _open_csv_text_stream(raw, blob_name) as stream:
            part_rows, _stats = _parse_csv_stream(
                stream,
                subscription_id,
                collect_rows=True,
                row_filter=row_filter,
            )
        del raw
        rows.extend(part_rows)
    return rows


# ── Cost-Management-query-shaped builders (blob rows only) ───────────────────

def _billing_currency(rows: list[dict]) -> str:
    for r in rows:
        if r.get("currency"):
            return r["currency"]
    return "USD"


def by_resource_response(rows: list[dict]) -> dict:
    agg: dict[str, dict] = {}
    for r in rows:
        rid = normalize_arm_id(r.get("resource_id") or "")
        if not rid:
            continue
        if rid not in agg:
            agg[rid] = {
                "PreTaxCost": 0.0, "CostUSD": 0.0,
                "ResourceType": r["resource_type"] or "",
                "ResourceGroup": r["resource_group"] or "",
                "ServiceName": r["service_name"] or "Other",
                "Currency": r["currency"] or "USD",
            }
        b = agg[rid]
        b["PreTaxCost"] += r["cost"]
        b["CostUSD"] += r["cost_usd"]
        if not b["ResourceType"] and r["resource_type"]:
            b["ResourceType"] = r["resource_type"]
        if not b["ResourceGroup"] and r["resource_group"]:
            b["ResourceGroup"] = r["resource_group"]
        if b["ServiceName"] == "Other" and r["service_name"]:
            b["ServiceName"] = r["service_name"]
        if r["currency"]:
            b["Currency"] = r["currency"]
    columns = [
        {"name": "ResourceId"}, {"name": "ResourceType"}, {"name": "ResourceGroup"},
        {"name": "ServiceName"}, {"name": "PreTaxCost"}, {"name": "CostUSD"}, {"name": "Currency"},
    ]
    out_rows = [
        [rid, b["ResourceType"], b["ResourceGroup"], b["ServiceName"],
         round(b["PreTaxCost"], 4), round(b["CostUSD"], 4), b["Currency"]]
        for rid, b in agg.items()
    ]
    log.info("cost_export.by_resource_built", input_rows=len(rows), resources=len(out_rows))
    return {"properties": {"columns": columns, "rows": out_rows}, "source": "blob_export"}


def by_service_response(rows: list[dict]) -> dict:
    agg: dict[str, dict] = {}
    for r in rows:
        svc = r["service_name"] or "Other"
        b = agg.setdefault(svc, {"PreTaxCost": 0.0, "CostUSD": 0.0, "Currency": r["currency"] or "USD"})
        b["PreTaxCost"] += r["cost"]
        b["CostUSD"] += r["cost_usd"]
        if r["currency"]:
            b["Currency"] = r["currency"]
    columns = [
        {"name": "ServiceName"}, {"name": "PreTaxCost"}, {"name": "CostUSD"}, {"name": "Currency"},
    ]
    out_rows = [
        [svc, round(b["PreTaxCost"], 4), round(b["CostUSD"], 4), b["Currency"]]
        for svc, b in sorted(agg.items(), key=lambda kv: kv[1]["PreTaxCost"], reverse=True)
    ]
    log.info("cost_export.by_service_built", input_rows=len(rows), services=len(out_rows))
    return {
        "properties": {"columns": columns, "rows": out_rows},
        "billing_currency": _billing_currency(rows),
        "source": "blob_export",
    }


def totals_response(rows: list[dict]) -> dict:
    columns = [{"name": "PreTaxCost"}, {"name": "CostUSD"}, {"name": "Currency"}]
    pretax = round(sum(r["cost"] for r in rows), 4)
    usd = round(sum(r["cost_usd"] for r in rows), 4)
    log.info("cost_export.totals_built", input_rows=len(rows), pretax=pretax, usd=usd)
    return {
        "properties": {"columns": columns, "rows": [[pretax, usd, _billing_currency(rows)]]},
        "source": "blob_export",
    }


def daily_response(rows: list[dict]) -> dict:
    agg: dict[tuple, dict] = {}
    for r in rows:
        key = (r["date"], r["resource_group"])
        b = agg.setdefault(key, {"PreTaxCost": 0.0, "CostUSD": 0.0, "Currency": r["currency"]})
        b["PreTaxCost"] += r["cost"]
        b["CostUSD"] += r["cost_usd"]
    columns = [
        {"name": "PreTaxCost"}, {"name": "CostUSD"}, {"name": "ResourceGroup"},
        {"name": "UsageDate"}, {"name": "Currency"},
    ]
    out_rows = [
        [round(b["PreTaxCost"], 4), round(b["CostUSD"], 4), rg, d, b["Currency"]]
        for (d, rg), b in sorted(agg.items())
    ]
    log.info("cost_export.daily_built", input_rows=len(rows), daily_points=len(out_rows))
    return {"properties": {"columns": columns, "rows": out_rows}, "source": "blob_export"}
