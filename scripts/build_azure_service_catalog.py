#!/usr/bin/env python3
"""Build data/azure_service_catalog.json from Azure Retail Prices API.

Run: python3 scripts/build_azure_service_catalog.py
Requires network access to https://prices.azure.com
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "azure_service_catalog.json"
REFERENCE_PATH = ROOT / "data" / "azure_free_tier_reference.json"
sys.path.insert(0, str(ROOT))

_TRIAL_SKU_MARKERS = ("trial", "preview", "evaluation")
_FREE_SKU_MARKERS = ("free", "f0", "free tier", "basic free")

SERVICE_FAMILIES = [
    "AI + Machine Learning",
    "Analytics",
    "Azure Communication Services",
    "Blockchain",
    "Compute",
    "Containers",
    "Data",
    "Databases",
    "Developer Tools",
    "Gaming",
    "Hybrid + Multicloud",
    "Integration",
    "Internet of Things",
    "Management and Governance",
    "Media",
    "Microsoft Syntex",
    "Mixed Reality",
    "Networking",
    "Other",
    "Quantum Computing",
    "SaaS",
    "Security",
    "Storage",
    "Web",
    "Windows Virtual Desktop",
]

# Cost Management / pricing-calculator names not always present in retail API pages.
MANUAL_SERVICES: dict[str, dict[str, Any]] = {
    "Azure Private Link": {
        "cost_type": "costed",
        "pricing_model": "pay_as_you_go",
        "free_tier": {
            "duration": "always",
            "limit": "Private Link service listed as free on Azure free services page",
            "notes": "Private endpoints still bill hourly and for data processed.",
            "doc_ref": "https://azure.microsoft.com/en-us/products/private-link/",
        },
        "notes": "Private endpoint hourly and data processing charges.",
    },
    "NAT Gateway": {
        "pricing_category": "Networking",
        "service_family": "Networking",
        "cost_type": "costed",
        "pricing_model": "pay_as_you_go",
        "notes": "Hourly and data processed charges.",
    },
    "Azure Virtual Network Manager": {
        "pricing_category": "Networking",
        "service_family": "Networking",
        "cost_type": "costed",
        "pricing_model": "pay_as_you_go",
        "notes": "Per subscription management fee plus per-VNet charges.",
    },
    "Azure Private 5G Core": {
        "pricing_category": "Networking",
        "service_family": "Networking",
        "cost_type": "costed",
        "pricing_model": "pay_as_you_go",
        "notes": "Private mobile network edge deployment.",
    },
    "Communications Gateway": {
        "pricing_category": "Networking",
        "service_family": "Networking",
        "cost_type": "costed",
        "pricing_model": "pay_as_you_go",
        "notes": "Operator connect gateway charges.",
    },
    "Elastic SAN": {
        "pricing_category": "Storage",
        "service_family": "Storage",
        "cost_type": "costed",
        "pricing_model": "pay_as_you_go",
        "notes": "Elastic SAN capacity and IOPS charges.",
    },
    "Static Web Apps": {
        "pricing_category": "Web",
        "service_family": "Web",
        "cost_type": "conditional",
        "pricing_model": "free_tier_limited",
        "free_tier": {
            "duration": "always",
            "limit": "100 GB bandwidth/month",
            "notes": "Free tier for static sites.",
        },
        "notes": "Free and Standard tiers.",
    },
}

# Curated overrides (better than retail-price inference alone).
SERVICE_OVERRIDES: dict[str, dict[str, Any]] = {
    "Virtual Network": {
        "cost_type": "conditional",
        "pricing_model": "hybrid",
        "free_tier": {
            "duration": "always",
            "limit": "50 virtual networks",
            "notes": "Base VNet resources are free; public IPs, gateways, and data transfer bill.",
            "doc_ref": "https://azure.microsoft.com/en-us/products/virtual-network/",
        },
    },
    "Network Watcher": {
        "cost_type": "conditional",
        "pricing_model": "hybrid",
        "free_tier": {
            "duration": "always",
            "limit": "5 GB storage with 1,000 checks, 10 tests, and 10 connection metrics",
            "notes": "Packet capture and flow logs bill.",
            "doc_ref": "https://azure.microsoft.com/en-us/products/network-watcher/",
        },
    },
    "Key Vault": {
        "cost_type": "conditional",
        "pricing_model": "hybrid",
        "free_tier": {
            "duration": "12_months_new_account",
            "limit": "10,000 transactions RSA 2048-bit keys or secret operations, Standard tier",
            "notes": "New-account allowance per Azure free services page; Standard SKU also has ongoing free operations.",
            "doc_ref": "https://azure.microsoft.com/en-us/products/key-vault/",
        },
    },
    "Container Registry": {
        "cost_type": "conditional",
        "pricing_model": "free_tier_12_months",
        "free_tier": {
            "duration": "12_months_new_account",
            "limit": "1 Standard tier registry with 100 GB storage and 10 webhooks",
            "notes": "New-account allowance; Basic SKU has no registry unit charge always.",
            "doc_ref": "https://azure.microsoft.com/en-us/products/container-registry/",
        },
    },
    "Storage": {
        "cost_type": "costed",
        "pricing_model": "free_tier_12_months",
        "free_tier": {
            "duration": "12_months_new_account",
            "limit": "5 GB LRS blob + 32 GB managed disks (new accounts)",
            "notes": "Azure free account allowances for 12 months.",
        },
    },
    "Azure Cosmos DB": {
        "cost_type": "costed",
        "pricing_model": "free_tier_monthly",
        "free_tier": {
            "duration": "always",
            "limit": "1,000 RU/s and 25 GB per subscription",
            "notes": "One free tier account per subscription.",
        },
    },
    "SQL Database": {
        "cost_type": "costed",
        "pricing_model": "free_tier_monthly",
        "free_tier": {
            "duration": "always",
            "limit": "Up to 10 serverless databases with 100,000 vCore seconds and 32 GB storage each",
            "notes": "Always-free allowance per Azure free services page.",
            "doc_ref": "https://azure.microsoft.com/en-us/products/azure-sql/database/",
        },
    },
    "Log Analytics": {
        "cost_type": "costed",
        "pricing_model": "free_tier_monthly",
        "free_tier": {
            "duration": "always",
            "limit": "5 GB ingestion/month per billing account",
            "notes": "Shared with Application Insights.",
        },
    },
    "Application Insights": {
        "cost_type": "conditional",
        "pricing_model": "free_tier_monthly",
        "free_tier": {
            "duration": "always",
            "limit": "5 GB ingestion/month",
            "notes": "Shared monitoring free allowance.",
        },
    },
    "Azure Monitor": {
        "cost_type": "conditional",
        "pricing_model": "hybrid",
        "free_tier": {
            "duration": "always",
            "limit": "Many alert and metric types included",
            "notes": "Ingestion and advanced features bill.",
        },
    },
    "Automation": {
        "cost_type": "conditional",
        "pricing_model": "free_tier_monthly",
        "free_tier": {
            "duration": "always",
            "limit": "500 job minutes/month",
            "notes": "Process automation free tier per subscription.",
        },
    },
    "API Management": {
        "cost_type": "costed",
        "pricing_model": "hybrid",
        "free_tier": {
            "duration": "always",
            "limit": "1 million calls/month on Consumption",
            "notes": "Consumption tier call allowance.",
        },
    },
    "Load Balancer": {
        "cost_type": "costed",
        "pricing_model": "hybrid",
        "free_tier": {
            "duration": "12_months_new_account",
            "limit": "750 hours, 15 GB data processing, and up to five rules with Standard Load Balancer",
            "notes": "New-account allowance; Basic SKU has no hourly charge always.",
            "doc_ref": "https://azure.microsoft.com/en-us/products/load-balancer/",
        },
    },
    "Virtual Machines": {
        "cost_type": "costed",
        "pricing_model": "reserved_capable",
    },
    "Azure Kubernetes Service": {
        "cost_type": "costed",
        "pricing_model": "hybrid",
        "free_tier": {
            "duration": "always",
            "limit": "Free tier control plane",
            "notes": "Node VM charges still apply.",
        },
    },
    "Microsoft Defender for Cloud": {
        "cost_type": "conditional",
        "pricing_model": "hybrid",
        "free_tier": {
            "duration": "always",
            "limit": "Secure score and basic CSPM features",
            "notes": "Defender plans bill per resource.",
        },
    },
    "Azure IoT Security": {
        "cost_type": "conditional",
        "pricing_model": "free_tier_limited",
    },
    "Azure Spring Cloud": {
        "cost_type": "conditional",
        "pricing_model": "free_tier_limited",
    },
    "Scheduler": {
        "cost_type": "free",
        "pricing_model": "always_free",
        "notes": "Azure Scheduler is retired; legacy meter may show $0.",
    },
    "Azure Policy": {
        "cost_type": "free",
        "pricing_model": "always_free",
        "notes": "Policy evaluation is free; guest configuration features may bill.",
    },
}

# Cost Management aliases → canonical retail service name.
SERVICE_ALIASES: dict[str, str] = {
    "kubernetes service": "Azure Kubernetes Service",
    "azure kubernetes service": "Azure Kubernetes Service",
    "azure cache for redis": "Redis Cache",
    "azure data factory": "Azure Data Factory v2",
    "data factory": "Azure Data Factory v2",
    "azure front door": "Azure Front Door Service",
    "content delivery network": "Content Delivery Network",
    "azure app service": "Azure App Service",
    "app service": "Azure App Service",
    "azure cognitive search": "Azure Cognitive Search",
    "virtual machines": "Virtual Machines",
    "virtual machine scale sets": "Virtual Machines",
    "backup": "Backup",
    "recovery services": "Backup",
    "microsoft.insights": "Application Insights",
    "azure machine learning": "Azure Machine Learning",
    "power bi embedded": "Power BI Embedded",
    "azure hdinsight": "HDInsight",
    "azure data explorer": "Azure Data Explorer",
    "azure synapse analytics": "Azure Synapse Analytics",
    "azure databricks": "Azure Databricks",
    "event hubs": "Event Hubs",
    "service bus": "Service Bus",
    "logic apps": "Logic Apps",
    "nat gateway": "NAT Gateway",
    "azure nat gateway": "NAT Gateway",
    "azure private link": "Azure Private Link",
    "private link": "Azure Private Link",
    "vpn gateway": "VPN Gateway",
    "virtual wan": "Virtual WAN",
    "expressroute": "ExpressRoute",
    "azure firewall": "Azure Firewall",
    "firewall manager": "Azure Firewall Manager",
    "route server": "Azure Route Server",
    "ip addresses": "Virtual Network",
    "bandwidth": "Bandwidth",
    "virtual network peering": "Virtual Network",
    "static web apps": "Static Web Apps",
    "signalr": "SignalR",
    "web pubsub": "Web PubSub",
    "redis cache": "Redis Cache",
    "sentinel": "Sentinel",
    "microsoft fabric": "Microsoft Fabric",
}


def _curl_json(url: str) -> dict[str, Any]:
    raw = subprocess.check_output(["curl", "-sS", "--max-time", "120", url], text=True)
    if not raw.strip():
        return {}
    return json.loads(raw)


def _merged_service_overrides() -> dict[str, dict[str, Any]]:
    from app.free_tier_reference import merged_service_catalog_overrides

    merged = {name: dict(override) for name, override in SERVICE_OVERRIDES.items()}
    for name, ref in merged_service_catalog_overrides().items():
        base = merged.get(name, {})
        free_tier = dict(ref.get("free_tier") or {})
        if base.get("free_tier"):
            base_ft = dict(base["free_tier"])
            for key, val in base_ft.items():
                if key not in free_tier or key == "notes":
                    free_tier[key] = val
        merged[name] = {**ref, **base, "free_tier": free_tier}
    return merged


def _infer_cost_type(has_zero: bool, has_paid: bool, sku_names: set[str] | list[str] | None = None) -> str:
    skus = [s for s in (sku_names or []) if s]
    sku_lower = [s.lower() for s in skus]
    trial_only = bool(skus) and all(any(m in s for m in _TRIAL_SKU_MARKERS) for s in sku_lower)
    has_trial_sku = any(any(m in s for m in _TRIAL_SKU_MARKERS) for s in sku_lower)

    if has_zero and not has_paid:
        if trial_only or (has_trial_sku and len(skus) <= 3):
            return "conditional"
        return "free"
    if has_zero and has_paid:
        return "conditional"
    return "costed"


def _infer_pricing_model(cost_type: str, has_zero: bool, sku_names: set[str] | list[str] | None = None) -> str:
    skus = [s for s in (sku_names or []) if s]
    sku_lower = [s.lower() for s in skus]
    if cost_type == "free":
        return "always_free"
    if cost_type == "conditional":
        if any(any(m in s for m in _TRIAL_SKU_MARKERS) for s in sku_lower):
            return "free_tier_limited"
        if has_zero:
            return "hybrid"
        return "pay_as_you_go"
    return "pay_as_you_go"


def _classify_sku_tier(sku_name: str, service_cost_type: str, service_pricing_model: str) -> dict[str, Any]:
    sku_lower = (sku_name or "").lower()
    if any(marker in sku_lower for marker in _TRIAL_SKU_MARKERS):
        return {
            "sku": sku_name,
            "pricing_model": "free_tier_limited",
            "cost_type": "conditional",
            "free_tier": {
                "duration": "trial",
                "limit": "Time-limited trial SKU",
                "notes": "Retail meter at $0 during trial; converts to paid after trial ends.",
                "doc_ref": "https://azure.microsoft.com/pricing/free-services",
            },
        }
    if any(marker in sku_lower for marker in _FREE_SKU_MARKERS):
        return {
            "sku": sku_name,
            "pricing_model": service_pricing_model if service_pricing_model != "pay_as_you_go" else "free_tier_limited",
            "cost_type": "conditional" if service_cost_type == "costed" else service_cost_type,
            "free_tier": {
                "duration": "always",
                "limit": f"Free SKU: {sku_name}",
                "notes": "Free tier SKU; overages or paid SKUs may bill.",
                "doc_ref": "https://azure.microsoft.com/pricing/free-services",
            },
        }
    return {
        "sku": sku_name,
        "pricing_model": service_pricing_model,
        "cost_type": service_cost_type,
    }


def _category_from_family(family: str) -> str:
    mapping = {
        "AI + Machine Learning": "AI",
        "Analytics": "Analytics",
        "Azure Communication Services": "Communication",
        "Blockchain": "Blockchain",
        "Compute": "Compute",
        "Containers": "Containers",
        "Data": "Data",
        "Databases": "Databases",
        "Developer Tools": "Developer Tools",
        "Gaming": "Gaming",
        "Integration": "Integration",
        "Internet of Things": "IoT",
        "Management and Governance": "Management",
        "Microsoft Syntex": "Productivity",
        "Mixed Reality": "Mixed Reality",
        "Networking": "Networking",
        "Quantum Computing": "Quantum",
        "Security": "Security",
        "Storage": "Storage",
        "Web": "Web",
        "Windows Virtual Desktop": "Desktop",
        "Other": "Other",
    }
    return mapping.get(family, family or "Other")


def fetch_retail_services() -> dict[str, dict[str, Any]]:
    services: dict[str, dict[str, Any]] = {}
    for fam in SERVICE_FAMILIES:
        filt = urllib.parse.quote(f"serviceFamily eq '{fam}'")
        url = f"https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview&$filter={filt}&$top=1000"
        pages = 0
        while url and pages < 200:
            try:
                data = _curl_json(url)
            except Exception:
                break
            if not data:
                break
            for item in data.get("Items", []):
                sn = item.get("serviceName")
                if not sn:
                    continue
                sf = item.get("serviceFamily") or fam
                price = float(item.get("retailPrice") or 0)
                entry = services.setdefault(
                    sn,
                    {
                        "service_family": sf,
                        "has_zero_price": False,
                        "has_paid_price": False,
                        "sku_names": set(),
                    },
                )
                entry["has_zero_price"] |= price == 0
                entry["has_paid_price"] |= price > 0
                sku = item.get("skuName")
                if sku and len(entry["sku_names"]) < 30:
                    entry["sku_names"].add(sku)
            url = data.get("NextPageLink")
            pages += 1
    return services


def build_catalog() -> dict[str, Any]:
    retail = fetch_retail_services()
    service_overrides = _merged_service_overrides()
    for name, manual in MANUAL_SERVICES.items():
        retail[name] = {
            "service_family": manual.get("service_family", "Other"),
            "has_zero_price": manual.get("cost_type") in {"free", "conditional"},
            "has_paid_price": manual.get("cost_type") != "free",
            "sku_names": set(),
            **manual,
        }

    services: list[dict[str, Any]] = []
    for name in sorted(retail):
        raw = retail[name]
        family = raw.get("service_family") or "Other"
        override = service_overrides.get(name, {})
        manual = MANUAL_SERVICES.get(name, {})
        sku_names = sorted(raw.get("sku_names") or [])[:20]

        cost_type = manual.get("cost_type") or override.get("cost_type")
        if not cost_type:
            cost_type = _infer_cost_type(
                raw.get("has_zero_price", False),
                raw.get("has_paid_price", True),
                sku_names,
            )

        pricing_model = manual.get("pricing_model") or override.get("pricing_model")
        if not pricing_model:
            pricing_model = _infer_pricing_model(
                cost_type,
                raw.get("has_zero_price", False),
                sku_names,
            )

        row: dict[str, Any] = {
            "service_name": name,
            "pricing_category": manual.get("pricing_category") or _category_from_family(family),
            "service_family": family,
            "cost_type": cost_type,
            "pricing_model": pricing_model,
            "notes": override.get("notes") or manual.get("notes") or f"Azure retail service ({family}).",
            "sku_tiers": [
                _classify_sku_tier(s, cost_type, pricing_model) for s in sku_names[:10]
            ],
            "sku_count": len(raw.get("sku_names") or []),
        }
        free_tier = override.get("free_tier") or manual.get("free_tier")
        if free_tier:
            row["free_tier"] = free_tier
        services.append(row)

    ref_doc: dict[str, Any] = {}
    if REFERENCE_PATH.is_file():
        with REFERENCE_PATH.open(encoding="utf-8") as fh:
            ref_doc = json.load(fh)

    from app.free_tier_reference import official_free_services_catalog

    official = official_free_services_catalog()

    return {
        "version": datetime.now(timezone.utc).strftime("%Y-%m"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "azure_retail_prices_api",
        "free_tier_reference_version": ref_doc.get("version"),
        "official_free_services_version": official.get("version"),
        "official_free_services_source": official.get("source_url"),
        "official_free_services_count": official.get("total_count"),
        "service_count": len(services),
        "aliases": SERVICE_ALIASES,
        "services": services,
    }


def main() -> None:
    catalog = build_catalog()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({catalog['service_count']} services)")


if __name__ == "__main__":
    main()
