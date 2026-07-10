"""Sidebar panel access policy — configurable per role by superuser."""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import SystemSetting
from app.user_auth import ROLE_ADMIN, ROLE_SUPERUSER, ROLE_VIEWER

NAV_ACCESS_CATEGORY = "nav_access"

# Mirrors frontend appRegistry sidebar entries (path = panel id).
NAV_PANEL_CATALOG: list[dict[str, Any]] = [
  # Overview
  {"id": "/", "label": "Dashboard", "group": "overview", "admin_only": False},
  {"id": "/costs", "label": "Cost explorer", "group": "overview", "admin_only": False},
  {"id": "/optimization-hub", "label": "Optimization hub", "group": "overview", "admin_only": False},
  # Advanced tools
  {"id": "/waste-heatmap", "label": "Waste heatmap", "group": "advanced", "admin_only": False},
  {"id": "/tag-compliance", "label": "Tag compliance", "group": "advanced", "admin_only": False},
  {"id": "/planned-maintenance", "label": "Planned maintenance", "group": "advanced", "admin_only": False},
  {"id": "/quota-usage", "label": "Quota usage", "group": "advanced", "admin_only": False},
  {"id": "/auto-scheduler", "label": "Auto scheduler", "group": "advanced", "admin_only": False},
  {"id": "/notifications", "label": "Notification channels", "group": "advanced", "admin_only": False},
  {"id": "/anomaly-detector", "label": "Anomaly detector", "group": "advanced", "admin_only": False},
  {"id": "/timeline", "label": "Optimization timeline", "group": "advanced", "admin_only": False},
  {"id": "/budgets", "label": "Budget manager", "group": "advanced", "admin_only": False},
  {"id": "/savings-planner", "label": "Savings planner", "group": "advanced", "admin_only": False},
  {"id": "/policy", "label": "Policy enforcement", "group": "advanced", "admin_only": False},
  {"id": "/reservation-advisor", "label": "Reservation advisor", "group": "advanced", "admin_only": False},
  {"id": "/governance", "label": "Governance dashboard", "group": "advanced", "admin_only": False},
  {"id": "/cost-allocation", "label": "Cost allocation", "group": "advanced", "admin_only": False},
  {"id": "/export-center", "label": "Export center", "group": "advanced", "admin_only": False},
  {"id": "/demand-forecaster", "label": "Demand forecaster", "group": "advanced", "admin_only": False},
  # System
  {"id": "/admin/optimization", "label": "Optimization center", "group": "system", "admin_only": True},
  {"id": "/history", "label": "Run history", "group": "system", "admin_only": False},
  {"id": "/engine", "label": "Engine rules", "group": "system", "admin_only": True},
  {"id": "/k8s", "label": "Cluster utilization", "group": "system", "admin_only": False},
  {"id": "/settings", "label": "Settings", "group": "system", "admin_only": True},
  {"id": "/admin/api-explorer", "label": "API explorer", "group": "system", "admin_only": True},
  # Resource inventory pages
  {"id": "/vms", "label": "Virtual machines", "group": "resources", "admin_only": False},
  {"id": "/vmss", "label": "VM scale sets", "group": "resources", "admin_only": False},
  {"id": "/disks", "label": "Managed disks", "group": "resources", "admin_only": False},
  {"id": "/snapshots", "label": "Disk snapshots", "group": "resources", "admin_only": False},
  {"id": "/aks", "label": "AKS clusters", "group": "resources", "admin_only": False},
  {"id": "/acr", "label": "Container registries", "group": "resources", "admin_only": False},
  {"id": "/appservices", "label": "App services", "group": "resources", "admin_only": False},
  {"id": "/appserviceplans", "label": "App service plans", "group": "resources", "admin_only": False},
  {"id": "/storage", "label": "Storage accounts", "group": "resources", "admin_only": False},
  {"id": "/publicips", "label": "Public IPs", "group": "resources", "admin_only": False},
  {"id": "/vnets", "label": "Virtual networks", "group": "resources", "admin_only": False},
  {"id": "/nics", "label": "Network interfaces", "group": "resources", "admin_only": False},
  {"id": "/natgateways", "label": "NAT gateways", "group": "resources", "admin_only": False},
  {"id": "/loadbalancers", "label": "Load balancers", "group": "resources", "admin_only": False},
  {"id": "/appgateways", "label": "Application gateways", "group": "resources", "admin_only": False},
  {"id": "/nsgs", "label": "Network security groups", "group": "resources", "admin_only": False},
  {"id": "/privateendpoints", "label": "Private endpoints", "group": "resources", "admin_only": False},
  {"id": "/privatelinkservices", "label": "Private link services", "group": "resources", "admin_only": False},
  {"id": "/privatedns", "label": "Private DNS zones", "group": "resources", "admin_only": False},
  {"id": "/sql", "label": "SQL databases", "group": "resources", "admin_only": False},
  {"id": "/cosmosdb", "label": "Cosmos DB", "group": "resources", "admin_only": False},
  {"id": "/postgresql", "label": "PostgreSQL", "group": "resources", "admin_only": False},
  {"id": "/redis", "label": "Redis cache", "group": "resources", "admin_only": False},
  {"id": "/keyvaults", "label": "Key vaults", "group": "resources", "admin_only": False},
]

# Subgroup ids mirror frontend ADVANCED_NAV_GROUPS / NAV_RESOURCE_GROUPS.
_ADVANCED_SUBGROUPS: dict[str, str] = {
  "/waste-heatmap": "advanced-insights",
  "/anomaly-detector": "advanced-insights",
  "/demand-forecaster": "advanced-insights",
  "/savings-planner": "advanced-savings",
  "/reservation-advisor": "advanced-savings",
  "/budgets": "advanced-savings",
  "/tag-compliance": "advanced-governance",
  "/policy": "advanced-governance",
  "/governance": "advanced-governance",
  "/planned-maintenance": "advanced-operations",
  "/quota-usage": "advanced-operations",
  "/auto-scheduler": "advanced-operations",
  "/notifications": "advanced-operations",
  "/timeline": "advanced-operations",
  "/cost-allocation": "advanced-operations",
  "/export-center": "advanced-operations",
}

_RESOURCE_SUBGROUPS: dict[str, str] = {
  "/vms": "compute",
  "/vmss": "compute",
  "/disks": "compute",
  "/snapshots": "compute",
  "/aks": "containers",
  "/acr": "containers",
  "/appservices": "appservices",
  "/appserviceplans": "appservices",
  "/storage": "storage",
  "/publicips": "networking",
  "/vnets": "networking",
  "/nics": "networking",
  "/natgateways": "networking",
  "/loadbalancers": "networking",
  "/appgateways": "networking",
  "/nsgs": "networking",
  "/privateendpoints": "networking",
  "/privatelinkservices": "networking",
  "/privatedns": "networking",
  "/sql": "databases",
  "/cosmosdb": "databases",
  "/postgresql": "databases",
  "/redis": "databases",
  "/keyvaults": "security",
}

_ADVANCED_SUBGROUP_LABELS: dict[str, str] = {
  "advanced-insights": "Cost insights",
  "advanced-savings": "Savings & budgets",
  "advanced-governance": "Governance",
  "advanced-operations": "Operations",
}

_RESOURCE_SUBGROUP_LABELS: dict[str, str] = {
  "compute": "Compute",
  "containers": "Containers",
  "appservices": "App services",
  "storage": "Storage",
  "networking": "Networking",
  "databases": "Databases",
  "security": "Security",
}


def _attach_panel_subgroups() -> None:
    for panel in NAV_PANEL_CATALOG:
        panel_id = panel["id"]
        if panel.get("group") == "advanced" and panel_id in _ADVANCED_SUBGROUPS:
            panel["subgroup"] = _ADVANCED_SUBGROUPS[panel_id]
        elif panel.get("group") == "resources" and panel_id in _RESOURCE_SUBGROUPS:
            panel["subgroup"] = _RESOURCE_SUBGROUPS[panel_id]


_attach_panel_subgroups()


def _build_section_catalog() -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = [
        {"id": "section:overview", "label": "Overview", "group": "overview", "kind": "section"},
        {"id": "section:advanced", "label": "Advanced tools", "group": "advanced", "kind": "section"},
        {"id": "section:resources", "label": "Resources", "group": "resources", "kind": "section"},
        {"id": "section:system", "label": "System", "group": "system", "kind": "section"},
    ]
    for subgroup_id, label in _ADVANCED_SUBGROUP_LABELS.items():
        sections.append({
            "id": f"section:advanced:{subgroup_id}",
            "label": label,
            "group": "advanced",
            "kind": "section",
            "parent": "section:advanced",
            "subgroup": subgroup_id,
        })
    for subgroup_id, label in _RESOURCE_SUBGROUP_LABELS.items():
        sections.append({
            "id": f"section:resources:{subgroup_id}",
            "label": label,
            "group": "resources",
            "kind": "section",
            "parent": "section:resources",
            "subgroup": subgroup_id,
        })
    return sections


NAV_SECTION_CATALOG: list[dict[str, Any]] = _build_section_catalog()
NAV_FULL_CATALOG: list[dict[str, Any]] = NAV_SECTION_CATALOG + NAV_PANEL_CATALOG

_CATALOG_BY_ID = {p["id"]: p for p in NAV_FULL_CATALOG}
_MANAGED_ROLES = (ROLE_ADMIN, ROLE_VIEWER)


def _default_visible(role: str, panel: dict[str, Any]) -> bool:
    if role == ROLE_ADMIN:
        return True
    if role == ROLE_VIEWER:
        return not panel.get("admin_only", False)
    return False


def default_nav_access_policy() -> dict[str, dict[str, bool]]:
    """Full default policy for admin and viewer roles."""
    policy: dict[str, dict[str, bool]] = {}
    for role in _MANAGED_ROLES:
        policy[role] = {
            entry["id"]: _default_visible(role, entry)
            for entry in NAV_FULL_CATALOG
            if entry.get("kind") != "section"
        }
        for section in NAV_SECTION_CATALOG:
            policy[role][section["id"]] = True
    return policy


def _load_policy_row(db: Session) -> SystemSetting | None:
    return db.query(SystemSetting).filter(SystemSetting.category == NAV_ACCESS_CATEGORY).first()


def get_nav_access_policy(db: Session) -> dict[str, dict[str, bool]]:
    """Return stored policy merged with defaults for unknown panels."""
    defaults = default_nav_access_policy()
    row = _load_policy_row(db)
    if not row or not row.config_json:
        return defaults
    try:
        stored = json.loads(row.config_json)
    except json.JSONDecodeError:
        return defaults
    roles = stored.get("roles") if isinstance(stored, dict) else None
    if not isinstance(roles, dict):
        return defaults

    merged = default_nav_access_policy()
    for role in _MANAGED_ROLES:
        role_cfg = roles.get(role)
        if not isinstance(role_cfg, dict):
            continue
        for panel_id, visible in role_cfg.items():
            if panel_id in _CATALOG_BY_ID and isinstance(visible, bool):
                merged[role][panel_id] = visible
    return merged


def save_nav_access_policy(db: Session, policy: dict[str, dict[str, bool]]) -> dict[str, dict[str, bool]]:
    """Persist policy for admin and viewer roles."""
    defaults = default_nav_access_policy()
    cleaned: dict[str, dict[str, bool]] = {}
    for role in _MANAGED_ROLES:
        role_in = policy.get(role) if isinstance(policy, dict) else None
        if not isinstance(role_in, dict):
            cleaned[role] = defaults[role]
            continue
        cleaned[role] = {
            panel_id: bool(role_in[panel_id])
            for panel_id in _CATALOG_BY_ID
            if panel_id in role_in
        }
        for panel_id, default_val in defaults[role].items():
            cleaned[role].setdefault(panel_id, default_val)

    payload = {"roles": cleaned}
    row = _load_policy_row(db)
    if row:
        row.config_json = json.dumps(payload)
    else:
        row = SystemSetting(
            id=str(uuid.uuid4()),
            category=NAV_ACCESS_CATEGORY,
            config_json=json.dumps(payload),
        )
        db.add(row)
    db.commit()
    return get_nav_access_policy(db)


def _sections_for_panel(panel_id: str) -> list[str]:
    panel = _CATALOG_BY_ID.get(panel_id)
    if not panel or panel.get("kind") == "section":
        return []
    group = panel.get("group")
    if not group:
        return []
    sections = [f"section:{group}"]
    subgroup = panel.get("subgroup")
    if subgroup:
        sections.append(f"section:{group}:{subgroup}")
    return sections


def _panel_allowed(panel_id: str, role: str, policy: dict[str, dict[str, bool]]) -> bool:
    panel = _CATALOG_BY_ID.get(panel_id)
    role_policy = policy.get(role, {})
    if panel_id in role_policy:
        return bool(role_policy[panel_id])
    if panel and panel.get("kind") == "section":
        return True
    if panel:
        return _default_visible(role, panel)
    return role != ROLE_VIEWER


def _path_allowed(panel_id: str, role: str, policy: dict[str, dict[str, bool]]) -> bool:
    for section_id in _sections_for_panel(panel_id):
        if not _panel_allowed(section_id, role, policy):
            return False
    return _panel_allowed(panel_id, role, policy)


def is_path_allowed(path: str, role: str, policy: dict[str, dict[str, bool]]) -> bool:
    """Check whether a sidebar route is visible for the given role."""
    if role == ROLE_SUPERUSER:
        return True

    normalized = path if path.startswith("/") else f"/{path}"
    if normalized != "/" and normalized.endswith("/"):
        normalized = normalized.rstrip("/")

    if _path_allowed(normalized, role, policy):
        return True

    # Dynamic per-type resource pages not listed in the catalog.
    if normalized.startswith("/") and normalized not in _CATALOG_BY_ID:
        return _path_allowed("section:resources", role, policy)

    return False


def allowed_paths_for_role(role: str, policy: dict[str, dict[str, bool]]) -> list[str]:
    if role == ROLE_SUPERUSER:
        return [entry["id"] for entry in NAV_FULL_CATALOG]
    paths = [
        entry["id"]
        for entry in NAV_FULL_CATALOG
        if entry.get("kind") == "section" and _panel_allowed(entry["id"], role, policy)
    ]
    paths.extend(
        panel["id"]
        for panel in NAV_PANEL_CATALOG
        if _path_allowed(panel["id"], role, policy)
    )
    if is_path_allowed("/vms", role, policy):
        if "section:resources" not in paths:
            paths.append("section:resources")
    return sorted(set(paths))


def nav_access_payload_for_user(role: str, db: Session) -> dict[str, Any]:
    policy = get_nav_access_policy(db)
    return {
        "role": role,
        "is_superuser": role == ROLE_SUPERUSER,
        "is_admin": role in (ROLE_ADMIN, ROLE_SUPERUSER),
        "allowed_paths": allowed_paths_for_role(role, policy),
        "catalog": NAV_PANEL_CATALOG,
        "sections": NAV_SECTION_CATALOG,
    }


def nav_access_policy_payload(db: Session) -> dict[str, Any]:
    return {
        "catalog": NAV_PANEL_CATALOG,
        "sections": NAV_SECTION_CATALOG,
        "roles": get_nav_access_policy(db),
        "defaults": default_nav_access_policy(),
    }
