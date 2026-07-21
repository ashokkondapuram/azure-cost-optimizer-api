#!/usr/bin/env python3
"""Sync Azure SKU specifications into it_services/<package>/data/sku_specs.json.

Run: python3 scripts/sync-azure-sku-specs.py
Optional: python3 scripts/sync-azure-sku-specs.py --fetch-retail-prices
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.azure_sku_defaults import AZURE_SKU_DEFAULTS

REGISTRY = ROOT / "packages" / "costoptimizer-core" / "service_registry.json"
ASSESSMENT_INDEX = ROOT / "data" / "assessment-index.json"
DATA_DIR = ROOT / "data"

LEGACY_DATA: dict[str, str] = {
    "compute/disk": "data/disk-assessment.json",
    "compute/vm": "data/vm-assessment.json",
    "compute/vmss": "data/vmss-assessment.json",
    "network/nat": "data/nat_gateway_metrics_thresholds.json",
    "network/loadbalancer": "data/load_balancer_metrics_thresholds.json",
    "network/appgateway": "data/app_gateway_metrics_thresholds.json",
    "network/publicip": "data/public_ip_metrics_thresholds.json",
    "storage/account": "data/storage_account_metrics_thresholds.json",
    "containers/aks": "data/aks_cluster_metrics_thresholds.json",
    "database/redis": "data/redis_sku_specifications.json",
    "database/postgresql": "data/postgresql_sku_specifications.json",
    "containers/acr": "data/acr_tier_specifications.json",
    "appservice/webapp": "data/app_service_tier_specifications.json",
    "appservice/plan": "data/app_service_tier_specifications.json",
}

RETAIL_SERVICE_NAMES: dict[str, str] = {
    "compute/vm": "Virtual Machines",
    "compute/disk": "Storage",
    "storage/account": "Storage",
    "database/sql": "SQL Database",
    "database/postgresql": "Azure Database for PostgreSQL",
    "database/redis": "Redis Cache",
    "containers/aks": "Azure Kubernetes Service",
    "network/appgateway": "Application Gateway",
    "network/nat": "NAT Gateway",
    "network/loadbalancer": "Load Balancer",
    "network/publicip": "Virtual Network",
    "integration/apim": "API Management",
    "monitoring/loganalytics": "Log Analytics",
    "search/cognitivesearch": "Azure Cognitive Search",
}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _assessment_path_for_arm(arm_type: str, index: dict[str, Any]) -> Path | None:
    for item in index.get("items") or []:
        if (item.get("resourceType") or "").lower() == arm_type.lower():
            filename = (item.get("assessmentFile") or "").strip()
            if filename:
                return DATA_DIR / filename
    return None


def _extract_skus_from_legacy(payload: dict[str, Any]) -> dict[str, Any]:
    skus: dict[str, Any] = {}
    for key in ("skus", "sku_tiers", "tiers", "disk_types"):
        block = payload.get(key)
        if isinstance(block, dict):
            skus.update(block)
    tier_specs = payload.get("disk_tier_specs")
    if isinstance(tier_specs, dict):
        for name, spec in tier_specs.items():
            skus.setdefault(name, spec)
    access = payload.get("access_tiers")
    if isinstance(access, dict):
        for name, spec in access.items():
            skus[f"access_{name}"] = spec
    replication = payload.get("replication")
    if isinstance(replication, dict):
        for name, spec in replication.items():
            skus[f"replication_{name}"] = spec
    families = payload.get("sku_families")
    if isinstance(families, dict):
        for name, spec in families.items():
            skus[f"family_{name}"] = spec
    return skus


def _extract_skus_from_assessment(payload: dict[str, Any]) -> dict[str, Any]:
    skus: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"disk_types", "premiumSsdPTiersFallback"} and isinstance(value, (dict, list)):
            if isinstance(value, dict):
                skus.update(value)
            elif isinstance(value, list):
                for row in value:
                    if isinstance(row, dict) and row.get("tier"):
                        skus[str(row["tier"])] = row
    tiers = payload.get("tiers")
    if isinstance(tiers, dict):
        skus.update(tiers)
    return skus


def _fetch_retail_sample(service_name: str, *, limit: int = 8) -> list[dict[str, Any]]:
    try:
        import urllib.request

        filt = quote(f"serviceName eq '{service_name}'")
        url = f"https://prices.azure.com/api/retail/prices?$filter={filt}&$top={limit}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for item in payload.get("Items") or []:
        rows.append({
            "sku_name": item.get("skuName"),
            "arm_sku_name": item.get("armSkuName"),
            "meter_name": item.get("meterName"),
            "unit_price": item.get("retailPrice"),
            "unit_of_measure": item.get("unitOfMeasure"),
            "currency": item.get("currencyCode"),
            "region": item.get("armRegionName"),
        })
    return rows


def build_sku_spec(
    row: dict[str, Any],
    *,
    fetch_retail: bool = False,
    assessment_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    canonical = (row.get("canonical_type") or "").strip().lower()
    service_id = row["service_id"]
    arm_type = row.get("arm_type") or ""
    package = service_id.replace("-", "_")

    legacy_rel = LEGACY_DATA.get(canonical)
    legacy_payload = _load_json(ROOT / legacy_rel) if legacy_rel else {}

    assessment_payload: dict[str, Any] = {}
    if assessment_index and arm_type:
        assessment_path = _assessment_path_for_arm(arm_type, assessment_index)
        if assessment_path:
            assessment_payload = _load_json(assessment_path)

    defaults = AZURE_SKU_DEFAULTS.get(canonical, {})
    skus = {}
    skus.update(defaults.get("skus") or {})
    skus.update(_extract_skus_from_legacy(legacy_payload))
    skus.update(_extract_skus_from_assessment(assessment_payload))

    documentation = dict(legacy_payload.get("documentation") or {})
    if assessment_payload.get("strategy"):
        documentation.setdefault(
            "pricing",
            (assessment_payload.get("apis") or {}).get("costManagement", {}).get("retailPrices", {}).get("url"),
        )

    spec: dict[str, Any] = {
        "schema_version": 1,
        "service_id": service_id,
        "canonical_type": canonical,
        "arm_type": arm_type,
        "display_name": row.get("display_name") or service_id,
        "source": "azure_docs_and_legacy_data",
        "documentation": documentation,
        "skus": skus,
        "pricing": {
            **(defaults.get("pricing") or {}),
            **(legacy_payload.get("pricing") or {}),
        },
        "optimization_thresholds": legacy_payload.get("optimization_thresholds") or {},
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }

    if fetch_retail:
        retail_name = RETAIL_SERVICE_NAMES.get(canonical)
        if retail_name:
            sample = _fetch_retail_sample(retail_name)
            if sample:
                spec["retail_price_samples"] = sample
                spec["source"] = "azure_retail_api_and_docs"

    return spec


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Azure SKU specs into it_services/*/data/")
    parser.add_argument(
        "--fetch-retail-prices",
        action="store_true",
        help="Enrich specs with Azure Retail Prices API samples (requires network)",
    )
    args = parser.parse_args()

    rows = json.loads(REGISTRY.read_text(encoding="utf-8"))
    assessment_index = _load_json(ASSESSMENT_INDEX)
    written = 0

    for row in rows:
        package = row["service_id"].replace("-", "_")
        out_dir = ROOT / "it_services" / package / "data"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "sku_specs.json"
        spec = build_sku_spec(
            row,
            fetch_retail=args.fetch_retail_prices,
            assessment_index=assessment_index,
        )
        out_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        written += 1

    # Refresh frontend disk tier subset from canonical disk spec
    disk_spec_path = ROOT / "it_services" / "compute_disk" / "data" / "sku_specs.json"
    frontend_path = ROOT / "frontend" / "src" / "it-services" / "compute-disk" / "data" / "disk_tier_specs.json"
    if disk_spec_path.is_file() and frontend_path.parent.is_dir():
        disk_spec = _load_json(disk_spec_path)
        tier_specs = {
            name: value
            for name, value in (disk_spec.get("skus") or {}).items()
            if isinstance(value, dict) and ("size_ranges" in value or "default_iops" in value)
        }
        if tier_specs:
            frontend_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "source": "it_services/compute_disk/data/sku_specs.json",
                        "disk_tier_specs": tier_specs,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

    print(f"Wrote {written} sku_specs.json files under it_services/*/data/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
