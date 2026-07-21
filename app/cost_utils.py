"""Shared helpers for Azure Cost Management (PreTaxCost / CostUSD) data."""

from __future__ import annotations

from typing import Any

from app.focus_mapping import normalize_arm_id


def cost_column_indices(columns: list) -> dict[str, int | None]:
    """Map Cost Management column names to row indices."""
    names = [c.get("name") if isinstance(c, dict) else c for c in columns]

    def _idx(*candidates: str) -> int | None:
        for name in candidates:
            if name in names:
                return names.index(name)
        return None

    return {
        "pretax": _idx("PreTaxCost", "Cost", "BilledCost", "CostInBillingCurrency"),
        "usd": _idx("CostUSD", "CostInUsd", "CostInUSD"),
        "currency": _idx("Currency", "BillingCurrency", "BillingCurrencyCode"),
        "resource_id": _idx("ResourceId"),
        "service_name": _idx("ServiceName", "MeterCategory", "ConsumedService", "x_SkuMeterCategory"),
        "meter_category": _idx("MeterCategory"),
        "consumed_service": _idx("ConsumedService"),
        "resource_type": _idx("ResourceType", "x_ResourceType"),
        "resource_group": _idx("ResourceGroup", "ResourceGroupName", "x_ResourceGroupName"),
        "usage_date": _idx("UsageDate", "BillingMonth", "ChargePeriodStart"),
    }


# Azure ConsumedService values (Microsoft.*) → Cost Management service labels.
_CONSUMED_SERVICE_LABELS: dict[str, str] = {
    "microsoft.compute": "Virtual Machines",
    "microsoft.storage": "Storage",
    "microsoft.network": "Virtual Network",
    "microsoft.containerservice": "Kubernetes Service",
    "microsoft.containerregistry": "Container Registry",
    "microsoft.sql": "SQL Database",
    "microsoft.documentdb": "Azure Cosmos DB",
    "microsoft.dbforpostgresql": "Azure Database for PostgreSQL",
    "microsoft.dbformysql": "Azure Database for MySQL",
    "microsoft.cache": "Azure Cache for Redis",
    "microsoft.web": "Azure App Service",
    "microsoft.keyvault": "Key Vault",
    "microsoft.operationalinsights": "Log Analytics",
    "microsoft.insights": "Application Insights",
    "microsoft.logic": "Logic Apps",
    "microsoft.datafactory": "Azure Data Factory",
    "microsoft.apimanagement": "API Management",
    "microsoft.eventhub": "Event Hubs",
    "microsoft.servicebus": "Service Bus",
    "microsoft.databricks": "Azure Databricks",
    "microsoft.synapse": "Azure Synapse Analytics",
    "microsoft.kusto": "Azure Data Explorer",
    "microsoft.machinelearningservices": "Azure Machine Learning",
    "microsoft.recoveryservices": "Backup",
    "microsoft.search": "Azure Cognitive Search",
    "microsoft.cdn": "Content Delivery Network",
}

# ARM resource type → Azure portal service label when ServiceName is blank.
_ARM_TYPE_SERVICE_LABELS: dict[str, str] = {
    "microsoft.compute/virtualmachines": "Virtual Machines",
    "microsoft.compute/virtualmachinescalesets": "Virtual Machine Scale Sets",
    "microsoft.compute/disks": "Storage",
    "microsoft.compute/snapshots": "Storage",
    "microsoft.storage/storageaccounts": "Storage",
    "microsoft.network/publicipaddresses": "Virtual Network",
    "microsoft.network/virtualnetworks": "Virtual Network",
    "microsoft.network/networkinterfaces": "Virtual Network",
    "microsoft.network/loadbalancers": "Load Balancer",
    "microsoft.network/applicationgateways": "Application Gateway",
    "microsoft.network/azurefirewalls": "Azure Firewall",
    "microsoft.network/natgateways": "Azure NAT Gateway",
    "microsoft.network/privateendpoints": "Azure Private Link",
    "microsoft.network/privatelinkservices": "Azure Private Link",
    "microsoft.network/privatednszones": "Azure Private Link",
    "microsoft.network/vpngateways": "VPN Gateway",
    "microsoft.network/virtualwans": "Virtual WAN",
    "microsoft.network/networkwatchers": "Network Watcher",
    "microsoft.containerservice/managedclusters": "Kubernetes Service",
    "microsoft.containerregistry/registries": "Container Registry",
    "microsoft.sql/servers": "SQL Database",
    "microsoft.sql/databases": "SQL Database",
    "microsoft.documentdb/databaseaccounts": "Azure Cosmos DB",
    "microsoft.dbforpostgresql/flexibleservers": "Azure Database for PostgreSQL",
    "microsoft.cache/redis": "Azure Cache for Redis",
    "microsoft.web/sites": "Azure App Service",
    "microsoft.web/serverfarms": "Azure App Service",
    "microsoft.keyvault/vaults": "Key Vault",
    "microsoft.operationalinsights/workspaces": "Log Analytics",
    "microsoft.insights/components": "Application Insights",
    "microsoft.logic/workflows": "Logic Apps",
    "microsoft.datafactory/factories": "Azure Data Factory",
    "microsoft.apimanagement/service": "API Management",
    "microsoft.eventhub/namespaces": "Event Hubs",
    "microsoft.servicebus/namespaces": "Service Bus",
    "microsoft.databricks/workspaces": "Azure Databricks",
    "microsoft.synapse/workspaces": "Azure Synapse Analytics",
    "microsoft.kusto/clusters": "Azure Data Explorer",
    "microsoft.machinelearningservices/workspaces": "Azure Machine Learning",
    "microsoft.recoveryservices/vaults": "Backup",
    "microsoft.search/searchservices": "Azure Cognitive Search",
    "microsoft.cdn/profiles": "Content Delivery Network",
}


def _label_from_consumed_service(value: str) -> str:
    key = (value or "").strip().lower()
    if not key:
        return ""
    if key in _CONSUMED_SERVICE_LABELS:
        return _CONSUMED_SERVICE_LABELS[key]
    # Microsoft.Storage → microsoft.storage
    if key.startswith("microsoft."):
        provider = key.split(".", 1)[0] + "." + key.split(".", 1)[1].split("/")[0]
        if provider in _CONSUMED_SERVICE_LABELS:
            return _CONSUMED_SERVICE_LABELS[provider]
    if key.startswith("microsoft."):
        slug = key.split(".", 1)[-1].split("/")[0]
        return slug.replace("/", " ").title()
    return value.strip()


def service_name_from_cost_row(
    row: list,
    idx: dict[str, int | None],
    *,
    names: list[str] | None = None,
) -> str:
    """Resolve Azure service label from a Cost Management row (never returns empty)."""
    col_names = names or []

    def _cell(key: str) -> str:
        i = idx.get(key)
        if i is None or i >= len(row):
            return ""
        return str(row[i] or "").strip()

    for key in ("service_name", "meter_category", "consumed_service"):
        raw = _cell(key)
        if not raw:
            continue
        if key in ("consumed_service", "service_name") and "." in raw and raw.lower().startswith("microsoft."):
            label = _label_from_consumed_service(raw)
            if label:
                return label
        if key == "consumed_service":
            label = _label_from_consumed_service(raw)
            if label:
                return label
        return raw

    for col_name in ("ServiceName", "MeterCategory", "ConsumedService", "x_SkuMeterCategory"):
        if col_name in col_names:
            raw = str(row[col_names.index(col_name)] or "").strip()
            if not raw:
                continue
            if col_name == "ConsumedService":
                label = _label_from_consumed_service(raw)
                if label:
                    return label
            else:
                return raw

    resource_type = _cell("resource_type").lower()
    if resource_type:
        if resource_type in _ARM_TYPE_SERVICE_LABELS:
            return _ARM_TYPE_SERVICE_LABELS[resource_type]
        provider = resource_type.split("/", 1)[0] if "/" in resource_type else resource_type
        label = _CONSUMED_SERVICE_LABELS.get(provider)
        if label:
            return label

    resource_id = normalize_arm_id(_cell("resource_id"))
    if resource_id and "/providers/" in resource_id:
        try:
            parts = resource_id.split("/")
            pidx = parts.index("providers")
            arm_type = f"{parts[pidx + 1]}/{parts[pidx + 2]}".lower()
            if arm_type in _ARM_TYPE_SERVICE_LABELS:
                return _ARM_TYPE_SERVICE_LABELS[arm_type]
            provider = parts[pidx + 1].lower()
            label = _CONSUMED_SERVICE_LABELS.get(provider)
            if label:
                return label
        except (ValueError, IndexError):
            pass

    return "Unassigned"


def service_label_for_arm_type(arm_type: str) -> str:
    """Azure Cost Management service label for an ARM provider/type."""
    key = (arm_type or "").strip().lower()
    if not key:
        return ""
    if key in _ARM_TYPE_SERVICE_LABELS:
        return _ARM_TYPE_SERVICE_LABELS[key]
    provider = key.split("/", 1)[0] if "/" in key else key
    return _CONSUMED_SERVICE_LABELS.get(provider, "")


def aggregate_cost_rows_by_service(response: dict) -> dict[str, dict]:
    """Sum PreTaxCost / CostUSD by resolved Azure service name from a query response."""
    from app.azure_cost import normalize_query_response

    props = normalize_query_response(response).get("properties") or {}
    cols = props.get("columns", [])
    names = [c.get("name") if isinstance(c, dict) else c for c in cols]
    idx = cost_column_indices(cols)
    if idx["pretax"] is None:
        return {}

    default_currency = str(response.get("billing_currency") or "CAD")
    agg: dict[str, dict] = {}
    for row in props.get("rows") or []:
        svc = service_name_from_cost_row(row, idx, names=names)
        pretax = float(row[idx["pretax"]]) if idx["pretax"] is not None else 0.0
        usd = float(row[idx["usd"]]) if idx["usd"] is not None else 0.0
        currency = (
            str(row[idx["currency"]]) if idx["currency"] is not None and row[idx["currency"]] else default_currency
        )
        bucket = agg.setdefault(
            svc,
            {"pretax": 0.0, "usd": 0.0, "currency": currency, "service_name": svc},
        )
        bucket["pretax"] += pretax
        bucket["usd"] += usd
        if currency:
            bucket["currency"] = currency
    return agg


def aggregate_cost_rows_by_resource_type(response: dict) -> dict[str, dict]:
    """Sum MTD costs by ARM ResourceType from a Cost Management query response."""
    from app.azure_cost import normalize_query_response

    props = normalize_query_response(response).get("properties") or {}
    cols = props.get("columns") or []
    idx = cost_column_indices(cols)
    if idx["resource_type"] is None or idx["pretax"] is None:
        return {}
    default_currency = response.get("billing_currency") or "CAD"
    agg: dict[str, dict] = {}
    for row in props.get("rows") or []:
        arm_type = str(row[idx["resource_type"]] or "").strip().lower()
        if not arm_type:
            continue
        pretax = float(row[idx["pretax"]])
        usd = float(row[idx["usd"]]) if idx["usd"] is not None else 0.0
        currency = (
            str(row[idx["currency"]]) if idx["currency"] is not None and row[idx["currency"]] else default_currency
        )
        bucket = agg.setdefault(
            arm_type,
            {"pretax": 0.0, "usd": 0.0, "currency": currency, "arm_resource_type": arm_type},
        )
        bucket["pretax"] += pretax
        bucket["usd"] += usd
        if currency:
            bucket["currency"] = currency
    return agg


def by_service_properties_from_response(response: dict) -> dict | None:
    """Normalize Azure by-service query rows to ServiceName / PreTaxCost / CostUSD / Currency."""
    agg = aggregate_cost_rows_by_service(response)
    if not agg:
        return None
    currency = str(response.get("billing_currency") or "CAD")
    buckets = sorted(agg.values(), key=lambda b: float(b.get("pretax") or 0), reverse=True)
    return {
        "columns": [
            {"name": "ServiceName"},
            {"name": "PreTaxCost"},
            {"name": "CostUSD"},
            {"name": "Currency"},
        ],
        "rows": [
            [
                b["service_name"],
                round(float(b.get("pretax") or 0), 4),
                round(float(b.get("usd") or 0), 4),
                b.get("currency") or currency,
            ]
            for b in buckets
        ],
    }


def merge_service_aggregates(*maps: dict[str, dict]) -> dict[str, dict]:
    """Merge multiple service→amount maps by summing pretax and USD."""
    merged: dict[str, dict] = {}
    for src in maps:
        for svc, bucket in src.items():
            entry = merged.setdefault(
                svc,
                {"pretax": 0.0, "usd": 0.0, "currency": bucket.get("currency") or "CAD", "service_name": svc},
            )
            entry["pretax"] += float(bucket.get("pretax") or 0.0)
            entry["usd"] += float(bucket.get("usd") or 0.0)
            if bucket.get("currency"):
                entry["currency"] = bucket["currency"]
    return merged


def summarize_cost_response(response: dict) -> dict:
    """Sum PreTaxCost (billing currency) and CostUSD from an Azure Cost Management query.

    Both values come directly from Azure — no FX conversion in this app.
    PreTaxCost is in the subscription billing currency (e.g. CAD).
    CostUSD is Azure's USD field for the same charges.
    """
    from app.azure_cost import normalize_query_response

    normalized = normalize_query_response(response)
    props = normalized.get("properties") or normalized
    cols = props.get("columns", [])
    rows = props.get("rows", [])
    idx = cost_column_indices(cols)

    pretax_total = 0.0
    usd_total = 0.0
    by_currency: dict[str, float] = {}

    for row in rows:
        pretax = _cell_amount(row, idx.get("pretax"))
        usd = _cell_amount(row, idx.get("usd"))
        currency = row[idx["currency"]] if idx.get("currency") is not None else None

        pretax_total += pretax
        usd_total += usd
        if currency:
            by_currency[str(currency)] = by_currency.get(str(currency), 0.0) + pretax

    billing_currency = normalized.get("billing_currency") or response.get("billing_currency")
    if not billing_currency and by_currency:
        billing_currency = max(by_currency, key=by_currency.get)

    return {
        "pretax_total": round(pretax_total, 2),
        "cost_usd_total": round(usd_total, 2),
        "billing_currency": billing_currency,
        "by_currency": {k: round(v, 2) for k, v in by_currency.items()},
        "row_count": len(rows),
        "source": normalized.get("source") or response.get("source") or "azure_cost_management",
    }


def _cell_amount(row: list, index: int | None) -> float:
    if index is None or index >= len(row):
        return 0.0
    try:
        return float(row[index] or 0.0)
    except (TypeError, ValueError):
        return 0.0


def subscription_totals_summary(response: dict) -> dict:
    """Extract subscription totals from query_subscription_totals or a raw API response."""
    try:
        pretax = float(response.get("pretax_total") or 0)
    except (TypeError, ValueError):
        pretax = 0.0
    try:
        usd = float(response.get("cost_usd_total") or 0)
    except (TypeError, ValueError):
        usd = 0.0
    if pretax or usd:
        return {
            "pretax_total": round(pretax, 2),
            "cost_usd_total": round(usd, 2),
            "billing_currency": response.get("billing_currency"),
            "row_count": int(response.get("row_count") or 0),
            "source": response.get("source") or "azure_cost_management",
        }
    return summarize_cost_response(response)


def parse_cost_by_resource_details(response: dict) -> dict[str, dict]:
    """Build resource-id → cost detail from export/API shape (sums across services)."""
    details: dict[str, dict] = {}
    props = response.get("properties") or {}
    cols = props.get("columns", [])
    idx = cost_column_indices(cols)
    names = [c.get("name") if isinstance(c, dict) else c for c in cols]
    if idx["resource_id"] is None or idx["pretax"] is None:
        return details
    for row in props.get("rows", []):
        rid = normalize_arm_id(row[idx["resource_id"]] or "")
        if not rid:
            continue
        pretax = float(row[idx["pretax"]])
        usd = float(row[idx["usd"]]) if idx["usd"] is not None else 0.0
        currency = str(row[idx["currency"]]) if idx["currency"] is not None and row[idx["currency"]] else "CAD"
        service = service_name_from_cost_row(row, idx, names=names)
        resource_group = (
            str(row[idx["resource_group"]]) if idx["resource_group"] is not None and row[idx["resource_group"]] else ""
        )
        resource_type = (
            str(row[idx["resource_type"]]) if idx["resource_type"] is not None and row[idx["resource_type"]] else ""
        )
        bucket = details.setdefault(rid, {
            "pretax": 0.0,
            "usd": 0.0,
            "currency": currency,
            "service_name": service,
            "resource_group": "",
            "resource_type": "",
        })
        bucket["pretax"] += pretax
        bucket["usd"] += usd
        if service and service != "Unassigned" and (
            not bucket["service_name"] or bucket["service_name"] == "Unassigned"
        ):
            bucket["service_name"] = service
        if currency:
            bucket["currency"] = currency
        if resource_group and not bucket["resource_group"]:
            bucket["resource_group"] = resource_group
        if resource_type and not bucket["resource_type"]:
            bucket["resource_type"] = resource_type
    return details


def by_resource_properties_from_response(response: dict) -> dict | None:
    """Normalize Azure by-resource query rows for API and export consumers."""
    from app.azure_cost import normalize_query_response

    details = parse_cost_by_resource_details(normalize_query_response(response))
    if not details:
        return None
    currency = str(response.get("billing_currency") or "CAD")
    sorted_items = sorted(
        details.items(),
        key=lambda kv: float(kv[1].get("pretax") or 0),
        reverse=True,
    )
    return {
        "columns": [
            {"name": "ResourceId"},
            {"name": "ResourceType"},
            {"name": "ResourceGroup"},
            {"name": "ServiceName"},
            {"name": "PreTaxCost"},
            {"name": "CostUSD"},
            {"name": "Currency"},
        ],
        "rows": [
            [
                rid,
                d.get("resource_type") or "",
                d.get("resource_group") or "",
                d.get("service_name") or "Other",
                round(float(d.get("pretax") or 0), 4),
                round(float(d.get("usd") or 0), 4),
                d.get("currency") or currency,
            ]
            for rid, d in sorted_items
        ],
    }


def parse_cost_by_resource(response: dict) -> dict[str, float]:
    """Build a resource-id → MTD PreTaxCost map (billing currency) from Azure."""
    costs: dict[str, float] = {}
    props = response.get("properties") or {}
    idx = cost_column_indices(props.get("columns", []))
    if idx["resource_id"] is None or idx["pretax"] is None:
        return costs
    for row in props.get("rows", []):
        rid = normalize_arm_id(row[idx["resource_id"]] or "")
        if not rid:
            continue
        costs[rid] = costs.get(rid, 0.0) + float(row[idx["pretax"]])
    return costs


def parse_cost_by_resource_usd(response: dict) -> dict[str, float]:
    """Build a resource-id → MTD CostUSD map from Azure."""
    costs: dict[str, float] = {}
    props = response.get("properties") or {}
    idx = cost_column_indices(props.get("columns", []))
    if idx["resource_id"] is None or idx["usd"] is None:
        return costs
    for row in props.get("rows", []):
        rid = normalize_arm_id(row[idx["resource_id"]] or "")
        if not rid:
            continue
        costs[rid] = costs.get(rid, 0.0) + float(row[idx["usd"]])
    return costs


def resource_cost(costs: dict[str, float], resource_id: str) -> float:
    """Return billed MTD cost for a resource, or 0 when not present in Cost Management."""
    return float(costs.get(normalize_arm_id(resource_id), 0.0))


def resolve_cost_map_entry(
    cost_map: dict[str, Any],
    resource_id: str,
) -> dict[str, Any] | None:
    """Lookup a per-resource MTD row using normalized ARM id."""
    if not cost_map or not resource_id:
        return None
    rid = normalize_arm_id(resource_id)
    if not rid:
        return None
    entry = cost_map.get(rid)
    if entry is None:
        return None
    if isinstance(entry, (int, float)):
        value = float(entry)
        return {"pretax": value, "usd": value, "currency": "USD"} if value > 0 else None
    if isinstance(entry, dict):
        return entry
    return None


def monthly_cost_from_snapshot(snap: Any) -> float:
    """Billing-currency MTD preferred, then USD, from a ResourceSnapshot ORM row."""
    if snap is None:
        return 0.0
    billing = float(getattr(snap, "monthly_cost_billing", 0) or 0)
    usd = float(getattr(snap, "monthly_cost_usd", 0) or 0)
    return billing if billing > 0 else usd


def monthly_cost_from_row_dict(row: dict[str, Any] | None) -> float:
    """Billing-currency MTD preferred, then USD, from a serialized inventory row."""
    billing, usd = monthly_cost_amounts_from_row(row or {})
    return billing if billing > 0 else usd


def monthly_cost_amounts_from_row(row: dict[str, Any]) -> tuple[float, float]:
    """Return (billing_currency_mtd, usd_mtd) already present on an inventory row."""
    try:
        billing = float(row.get("monthlyCostBilling") if row.get("monthlyCostBilling") is not None else row.get("monthly_cost_billing") or 0)
    except (TypeError, ValueError):
        billing = 0.0
    try:
        usd = float(row.get("monthlyCostUsd") if row.get("monthlyCostUsd") is not None else row.get("monthly_cost_usd") or 0)
    except (TypeError, ValueError):
        usd = 0.0
    return billing, usd


def monthly_cost_amounts_from_cost_block(cost: dict[str, Any] | None) -> tuple[float, float, str]:
    """Return (billing, usd, currency) from a persisted enrichment cost_json block."""
    if not isinstance(cost, dict) or not cost:
        return 0.0, 0.0, "USD"

    def _amount(keys: tuple[str, ...]) -> float:
        for key in keys:
            if key not in cost or cost.get(key) is None:
                continue
            try:
                value = float(cost[key])
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        return 0.0

    billing = _amount(("cost_billing", "pretax", "monthly_cost_billing", "monthlyCostBilling"))
    usd = _amount(("cost_usd", "usd", "monthly_cost_usd", "monthlyCostUsd"))
    if billing <= 0 and usd <= 0:
        try:
            actual = float(cost.get("monthlyActualCost") or 0)
        except (TypeError, ValueError):
            actual = 0.0
        if actual > 0:
            billing = actual
    currency = str(
        cost.get("billingCurrency")
        or cost.get("billing_currency")
        or cost.get("currency")
        or "USD"
    )
    return billing, usd, currency


def build_resource_cost_envelope(
    *,
    billing: float = 0.0,
    usd: float = 0.0,
    currency: str = "CAD",
    retail_monthly: float | None = None,
    retail_currency: str | None = None,
    retail_source: str | None = None,
    retail_pending: bool = True,
    cost_pending: bool | None = None,
) -> dict[str, Any]:
    """Canonical nested cost block for API rows and enrichment."""
    billed = billing if billing > 0 else (usd if usd > 0 else 0.0)
    pending = cost_pending if cost_pending is not None else billed <= 0
    envelope = {
        "billed_mtd": round(billed, 2) if billed > 0 else 0.0,
        "billed_currency": currency or "CAD",
        "retail_monthly": round(retail_monthly, 2) if retail_monthly and retail_monthly > 0 else None,
        "retail_currency": retail_currency or currency or "CAD",
        "retail_source": retail_source,
        "cost_pending": pending,
        "retail_pending": retail_pending if retail_monthly is None else False,
    }
    return envelope


def attach_cost_envelope_to_row(row: dict[str, Any], envelope: dict[str, Any]) -> dict[str, Any]:
    """Apply canonical cost envelope to a resource row (flat + nested fields)."""
    if not envelope:
        return row
    billed = float(envelope.get("billed_mtd") or 0)
    currency = str(envelope.get("billed_currency") or row.get("billingCurrency") or "CAD")
    if billed > 0:
        row["monthlyCostBilling"] = billed
        row["monthly_cost_billing"] = billed
    retail = envelope.get("retail_monthly")
    if retail is not None and float(retail) > 0:
        row["retailMonthly"] = float(retail)
        row["retail_monthly"] = float(retail)
        row["retailCurrency"] = envelope.get("retail_currency") or currency
        row["retail_currency"] = row["retailCurrency"]
        row["retailSource"] = envelope.get("retail_source")
        row["retail_source"] = row["retailSource"]
    row["costPending"] = bool(envelope.get("cost_pending"))
    row["cost_pending"] = row["costPending"]
    row["retailPending"] = bool(envelope.get("retail_pending"))
    row["billingCurrency"] = currency
    row["billing_currency"] = currency
    row["cost"] = envelope
    _apply_assessment_cost_normalized_keys(row, envelope)
    return row


def _apply_assessment_cost_normalized_keys(row: dict[str, Any], envelope: dict[str, Any]) -> None:
    """Map assessment cost_management field names to normalized row keys (disks today)."""
    canonical = (row.get("type") or row.get("canonical_type") or row.get("_canonical_type") or "").strip().lower()
    if canonical != "compute/disk":
        return
    try:
        from it_services.compute_disk.assessment_bridge import cost_field_mapping
    except ImportError:
        return
    for field, normalized in cost_field_mapping().items():
        if not normalized:
            continue
        value = envelope.get(field)
        if value is None:
            continue
        row[normalized] = value
        if normalized == "monthly_cost_usd" and float(value or 0) > 0:
            row["monthlyCostUsd"] = float(value)
            row["monthly_cost_usd"] = float(value)


def finalize_cost_block(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize mixed overlay/snapshot keys into canonical enrichment cost fields."""
    billing, usd, currency = monthly_cost_amounts_from_cost_block(payload)
    out = dict(payload)
    if billing > 0:
        out["monthly_cost_billing"] = billing
        out["monthlyCostBilling"] = billing
    if usd > 0:
        out["monthly_cost_usd"] = usd
        out["monthlyCostUsd"] = usd
    if billing > 0 or usd > 0:
        out["monthlyActualCost"] = billing if billing > 0 else usd
    if currency:
        out["billingCurrency"] = currency
        out["billing_currency"] = currency

    retail_monthly = payload.get("retail_monthly")
    if retail_monthly is None:
        retail_monthly = payload.get("retailMonthly")
    retail_source = payload.get("retail_source") or payload.get("retailSource")
    retail_currency = payload.get("retail_currency") or payload.get("retailCurrency")
    retail_pending = payload.get("retail_pending")
    if retail_pending is None:
        retail_pending = payload.get("retailPending")
    cost_pending = payload.get("cost_pending")
    if cost_pending is None:
        cost_pending = payload.get("costPending")

    envelope = build_resource_cost_envelope(
        billing=billing,
        usd=usd,
        currency=currency,
        retail_monthly=float(retail_monthly) if retail_monthly is not None else None,
        retail_currency=str(retail_currency) if retail_currency else None,
        retail_source=str(retail_source) if retail_source else None,
        retail_pending=bool(retail_pending) if retail_pending is not None else retail_monthly is None,
        cost_pending=bool(cost_pending) if cost_pending is not None else None,
    )
    out["cost"] = envelope
    out.update(envelope)
    return out


def monthly_cost_amounts_from_entry(entry: dict[str, Any]) -> tuple[float, float, str]:
    """Return (billing, usd, currency) from a cost-map detail row."""
    try:
        billing = float(entry.get("pretax") if entry.get("pretax") is not None else entry.get("cost_billing") or 0)
    except (TypeError, ValueError):
        billing = 0.0
    try:
        usd = float(entry.get("usd") if entry.get("usd") is not None else entry.get("cost_usd") or 0)
    except (TypeError, ValueError):
        usd = 0.0
    currency = str(entry.get("currency") or entry.get("billing_currency") or "CAD")
    return billing, usd, currency


def _billing_from_cost_entry(entry: dict[str, Any]) -> float | None:
    """Extract MTD PreTaxCost in billing currency as reported by Azure."""
    try:
        pretax = float(entry.get("pretax") or 0)
    except (TypeError, ValueError):
        return None
    return pretax if pretax > 0 else None


def billing_cost_map_from_details(cost_details: dict[str, dict]) -> dict[str, float]:
    """Resource-id → MTD cost in billing currency (PreTaxCost, e.g. CAD)."""
    out: dict[str, float] = {}
    for rid, detail in cost_details.items():
        billing = _billing_from_cost_entry(detail)
        if billing is not None:
            out[rid] = billing
    return out


def resource_cost_billing_from_map(
    cost_map: dict[str, Any],
    resource_id: str,
) -> float | None:
    """Extract MTD billing-currency cost from a cost-map entry, or None when absent."""
    if not resource_id:
        return None
    entry = cost_map.get(normalize_arm_id(resource_id))
    if entry is None:
        return None
    if isinstance(entry, (int, float)):
        try:
            value = float(entry)
            return value if value > 0 else None
        except (TypeError, ValueError):
            return None
    if isinstance(entry, dict):
        return _billing_from_cost_entry(entry)
    return None


def _usd_from_cost_entry(entry: dict[str, Any]) -> float | None:
    """Extract a positive USD MTD value from a cost-map detail row."""
    try:
        usd = float(entry.get("usd") or 0)
    except (TypeError, ValueError):
        return None
    if usd > 0:
        return usd
    currency = (entry.get("currency") or "USD").upper()
    if currency != "USD":
        return None
    try:
        pretax = float(entry.get("pretax") or 0)
    except (TypeError, ValueError):
        return None
    return pretax if pretax > 0 else None


def usd_cost_map_from_details(cost_details: dict[str, dict]) -> dict[str, float]:
    """Convert per-resource detail rows to resource-id → MTD USD for the optimizer."""
    out: dict[str, float] = {}
    for rid in cost_details:
        usd = resource_cost_usd_from_map(cost_details, rid)
        if usd is not None:
            out[rid] = usd
    return out


def resource_cost_usd_from_map(
    cost_map: dict[str, Any],
    resource_id: str,
) -> float | None:
    """Extract MTD USD from ``resource_cost_map_from_db`` entry, or None when absent."""
    if not resource_id:
        return None
    entry = cost_map.get(normalize_arm_id(resource_id))
    if entry is None:
        return None
    if isinstance(entry, (int, float)):
        try:
            value = float(entry)
            return value if value > 0 else None
        except (TypeError, ValueError):
            return None
    if isinstance(entry, dict):
        return _usd_from_cost_entry(entry)
    return None


def normalize_monthly_cost_usd(value: Any) -> float | None:
    """Coerce API/DB cost payloads to a positive USD float, or None."""
    if value is None:
        return None
    if isinstance(value, dict):
        if "usd" in value or "pretax" in value or "currency" in value:
            return _usd_from_cost_entry(value)
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return None
    return amount if amount > 0 else None


def project_mtd_to_monthly_run_rate(
    mtd_cost_usd: float,
    *,
    as_of: Any | None = None,
) -> float:
    """Project month-to-date billed cost to a full-month run-rate (Advisor-style baseline)."""
    if mtd_cost_usd <= 0:
        return 0.0
    from datetime import date
    import calendar

    today = as_of if isinstance(as_of, date) else date.today()
    days_elapsed = max(1, today.day)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    return round(mtd_cost_usd * (days_in_month / days_elapsed), 2)


def savings_from_factor(baseline: float, factor: float) -> float:
    """Apply a savings factor to a billed baseline; returns 0 when baseline is unknown."""
    if baseline <= 0:
        return 0.0
    return round(baseline * factor, 2)


def savings_from_retail_delta(pricing: dict[str, Any] | None) -> float:
    """Extract estimated monthly savings from an Azure retail pricing payload."""
    if not pricing:
        return 0.0
    value = pricing.get("estimated_monthly_savings_usd")
    if value is None:
        value = pricing.get("retail_monthly_savings_usd")
    try:
        return max(0.0, round(float(value or 0), 2))
    except (TypeError, ValueError):
        return 0.0


def aks_pool_cost_share(cluster_cost: float, pool_node_count: int, total_nodes: int) -> float:
    """Allocate cluster MTD cost to a node pool by node count share."""
    if cluster_cost <= 0 or total_nodes <= 0 or pool_node_count <= 0:
        return 0.0
    return round(cluster_cost * (pool_node_count / total_nodes), 2)
