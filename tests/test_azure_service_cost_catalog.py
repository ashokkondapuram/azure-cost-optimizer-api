"""Azure service cost classification catalog."""

from __future__ import annotations

from app.azure_service_cost_catalog import (
    classify_resource_type,
    cost_type_for_arm_type,
    cost_type_for_canonical,
    cost_type_for_service_name,
    is_cost_bearing_type,
)


def test_networking_services_from_pricing_calculator():
    assert cost_type_for_service_name("Azure Private Link") == "costed"
    assert cost_type_for_service_name("NAT Gateway") == "costed"
    assert cost_type_for_service_name("Load Balancer") == "costed"
    assert cost_type_for_service_name("Virtual Network") == "conditional"
    assert cost_type_for_service_name("Network Watcher") == "conditional"


def test_full_catalog_covers_all_azure_services():
    from app.azure_service_cost_catalog import catalog_metadata, catalog_table_rows

    meta = catalog_metadata()
    rows = catalog_table_rows()
    assert meta["service_count"] >= 150
    assert len(rows) >= 150
    families = {row.get("service_family") for row in rows}
    assert "Networking" in families
    assert "AI + Machine Learning" in families
    assert "Security" in families


def test_service_alias_resolution():
    from app.azure_service_cost_catalog import resolve_service_name

    assert resolve_service_name("Kubernetes Service") == "Azure Kubernetes Service"
    assert resolve_service_name("azure private link") == "Azure Private Link"
    assert resolve_service_name("Azure Cache for Redis") == "Redis Cache"


def test_arm_and_canonical_mappings():
    assert cost_type_for_arm_type("microsoft.network/privateendpoints") == "costed"
    assert cost_type_for_arm_type("microsoft.network/networksecuritygroups") == "free"
    assert cost_type_for_canonical("network/privateendpoint") == "costed"
    assert cost_type_for_canonical("network/nsg") == "free"
    assert cost_type_for_canonical("network/vnet") == "conditional"


def test_managed_identity_is_free():
    assert cost_type_for_arm_type("microsoft.managedidentity/userassignedidentities") == "free"
    assert is_cost_bearing_type(
        arm_type="microsoft.managedidentity/userassignedidentities",
        resource_count=100,
    ) is False


def test_costed_type_with_inventory_is_cost_bearing_without_mtd():
    assert is_cost_bearing_type(
        canonical_type="network/privateendpoint",
        resource_count=10,
        cost_mtd=0.0,
    ) is True


def test_conditional_type_hidden_without_mtd():
    row = classify_resource_type(canonical_type="network/vnet", cost_mtd=0.0)
    assert row.cost_type == "conditional"
    assert row.visible_on_dashboard(0.0, inventory=5) is False
    assert row.visible_on_dashboard(12.5, inventory=5) is True


def test_private_endpoint_visible_on_dashboard_with_inventory():
    row = classify_resource_type(canonical_type="network/privateendpoint", cost_mtd=0.0)
    assert row.visible_on_dashboard(0.0, inventory=10) is True


def test_nsg_classification_includes_free_tier_metadata():
    row = classify_resource_type(
        canonical_type="network/nsg",
        arm_type="microsoft.network/networksecuritygroups",
    )
    assert row.cost_type == "free"
    assert row.free_tier is not None
    assert row.free_tier["duration"] == "always"
    assert "doc_ref" in row.free_tier


def test_trial_only_services_reclassified_from_retail_inference():
    from app.azure_service_cost_catalog import service_catalog_row

    power_bi = service_catalog_row("Power BI")
    assert power_bi is not None
    assert power_bi["cost_type"] == "costed"

    playwright = service_catalog_row("Microsoft Playwright Testing")
    if playwright:
        assert playwright["cost_type"] == "conditional"
        assert playwright.get("free_tier", {}).get("duration") in {"always", "trial"}


def test_arm_type_catalog_rows_include_free_tier():
    from app.azure_service_cost_catalog import arm_type_catalog_rows

    rows = {row["arm_type"]: row for row in arm_type_catalog_rows()}
    nsg = rows["microsoft.network/networksecuritygroups"]
    assert nsg["cost_type"] == "free"
    assert nsg.get("free_tier", {}).get("duration") == "always"


def test_free_tier_reference_metadata():
    from app.free_tier_reference import official_free_services_catalog, reference_metadata

    meta = reference_metadata()
    assert meta["arm_type_count"] >= 20
    assert meta["service_override_count"] >= 10
    assert meta["account_programs"]["30_days_credit"]["duration"] == "30_days_new_account"

    official = official_free_services_catalog()
    assert official["always_count"] >= 40
    assert official["twelve_month_count"] >= 15
    assert official["source_url"].endswith("#List-of-free-services")


def test_official_free_services_mapped_to_retail_catalog():
    from app.azure_service_cost_catalog import service_catalog_row
    from app.free_tier_reference import official_free_tier_for_service

    aks = service_catalog_row("Azure Kubernetes Service")
    assert aks is not None
    assert aks.get("free_tier", {}).get("limit", "").lower().find("cluster management") >= 0

    kv = official_free_tier_for_service("Key Vault")
    assert kv is not None
    assert kv["duration"] == "12_months_new_account"
    assert "10,000" in kv["limit"]

    cosmos = service_catalog_row("Azure Cosmos DB")
    assert cosmos is not None
    ft = cosmos.get("free_tier") or {}
    assert "1,000" in ft.get("limit", "") or "400" in ft.get("limit", "")
