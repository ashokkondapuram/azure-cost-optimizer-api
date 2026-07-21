"""Resolve canonical resource types to their single assessment JSON config file."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.assessment.bridge import load_assessment_for_canonical, optimization_thresholds
from app.assessment.catalog import assessment_data_dir, get_assessment_for_arm_type, load_assessment_index
from app.assessment.bridge import arm_type_for_canonical

_ROOT = Path(__file__).resolve().parents[2]

# Legacy threshold files — superseded by *-assessment.json when sections are merged.
_LEGACY_THRESHOLD_FILES: dict[str, str] = {
    "analytics/databricks": "data/databricks_metrics_thresholds.json",
    "analytics/synapse": "data/synapse_metrics_thresholds.json",
    "analytics/adx": "data/adx_metrics_thresholds.json",
    "analytics/mlworkspace": "data/mlworkspace_metrics_thresholds.json",
    "integration/apim": "data/apim_metrics_thresholds.json",
    "integration/datafactory": "data/datafactory_metrics_thresholds.json",
    "integration/logicapp": "data/logicapp_metrics_thresholds.json",
    "messaging/eventhub": "data/eventhub_metrics_thresholds.json",
    "messaging/servicebus": "data/servicebus_metrics_thresholds.json",
    "monitoring/loganalytics": "data/loganalytics_metrics_thresholds.json",
    "monitoring/appinsights": "data/appinsights_metrics_thresholds.json",
    "backup/recoveryvault": "data/recoveryvault_metrics_thresholds.json",
    "search/cognitivesearch": "data/cognitivesearch_metrics_thresholds.json",
    "network/frontdoor": "data/frontdoor_metrics_thresholds.json",
    "compute/vm": "data/vm-assessment.json",
    "compute/vmss": "data/vmss-assessment.json",
    "compute/disk": "data/disk-assessment.json",
    "compute/snapshot": "data/snapshot_metrics_thresholds.json",
    "containers/aks": "data/aks_cluster_metrics_thresholds.json",
    "containers/acr": "data/acr_metrics_thresholds.json",
    "storage/account": "data/storage_account_metrics_thresholds.json",
    "network/publicip": "data/public_ip_metrics_thresholds.json",
    "network/nic": "data/nic_metrics_thresholds.json",
    "network/nat": "data/nat_gateway_metrics_thresholds.json",
    "network/loadbalancer": "data/load_balancer_metrics_thresholds.json",
    "network/appgateway": "data/app_gateway_metrics_thresholds.json",
    "network/nsg": "data/nsg_metrics_thresholds.json",
    "database/sql": "data/sql_database_metrics_thresholds.json",
    "database/cosmosdb": "data/cosmosdb-assessment.json",
    "database/postgresql": "data/postgresql_metrics_thresholds.json",
    "database/redis": "data/redis_metrics_thresholds.json",
    "appservice/webapp": "data/app_service_metrics_thresholds.json",
    "appservice/plan": "data/app_service_metrics_thresholds.json",
    "governance": "data/governance_metrics_thresholds.json",
    "cost_anomalies": "data/cost_anomaly_metrics_thresholds.json",
}


@lru_cache(maxsize=1)
def _canonical_to_assessment_file() -> dict[str, str]:
    from app.resource_type_map import ARM_PROVIDER_TO_INTERNAL

    index = load_assessment_index()
    arm_to_file: dict[str, str] = {}
    for item in index.get("items") or []:
        arm_type = str(item.get("resourceType") or "").strip().lower()
        assessment_file = str(item.get("assessmentFile") or "").strip()
        if arm_type and assessment_file:
            arm_to_file[arm_type] = assessment_file

    mapping: dict[str, str] = {}
    for arm_type, canonical in ARM_PROVIDER_TO_INTERNAL.items():
        filename = arm_to_file.get(arm_type.lower())
        if filename:
            mapping[canonical] = filename
    # Disk is canonical even when index uses Microsoft.Compute/disks
    mapping.setdefault("compute/disk", "disk-assessment.json")
    mapping.setdefault("database/cosmosdb", "cosmosdb-assessment.json")
    return mapping


def assessment_file_for_canonical(canonical_type: str) -> str | None:
    return _canonical_to_assessment_file().get((canonical_type or "").strip().lower())


def assessment_path_for_canonical(canonical_type: str) -> Path | None:
    filename = assessment_file_for_canonical(canonical_type)
    if not filename:
        return None
    path = assessment_data_dir() / filename
    return path if path.is_file() else None


@lru_cache(maxsize=64)
def load_resource_config(canonical_type: str) -> dict[str, Any]:
    """Single source of truth: assessment JSON, with legacy threshold file fallback."""
    ct = (canonical_type or "").strip().lower()
    assessment = load_assessment_for_canonical(ct)
    if assessment:
        return assessment

    legacy_rel = _LEGACY_THRESHOLD_FILES.get(ct)
    if legacy_rel:
        path = _ROOT / legacy_rel
        if path.is_file():
            with path.open(encoding="utf-8") as fh:
                data = json.load(fh)
            data["_file"] = path.name
            return data
    return {}


def load_optimization_thresholds(canonical_type: str) -> dict[str, float]:
    config = load_resource_config(canonical_type)
    if config:
        thresholds = optimization_thresholds(config)
        if thresholds:
            return thresholds
    legacy_rel = _LEGACY_THRESHOLD_FILES.get((canonical_type or "").strip().lower())
    if not legacy_rel:
        return {}
    path = _ROOT / legacy_rel
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as fh:
        raw = json.load(fh).get("optimization_thresholds") or {}
    return {k: float(v) for k, v in raw.items() if v is not None}


def clear_config_resolver_cache() -> None:
    _canonical_to_assessment_file.cache_clear()
    load_resource_config.cache_clear()
    load_assessment_index.cache_clear()
    get_assessment_for_arm_type.cache_clear()
