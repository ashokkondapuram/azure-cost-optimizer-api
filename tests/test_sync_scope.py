"""Tests for scoped sync type mapping."""

from app.sync_scope import canonical_type_from_api_path, types_for_api_path


def test_vmss_api_path_maps_to_compute_vmss():
    assert canonical_type_from_api_path("/resources/vmss") == "compute/vmss"
    assert types_for_api_path("/resources/vmss") == ["compute/vmss"]


def test_vms_api_path_still_maps_to_compute_vm():
    assert canonical_type_from_api_path("/resources/vms") == "compute/vm"
    assert types_for_api_path("/resources/vms") == ["compute/vm"]


def test_loganalytics_api_path_maps_to_single_type():
    types = types_for_api_path("/resources/loganalytics")
    assert types == ["monitoring/loganalytics"]


def test_legacy_monitoring_aggregate_still_maps_to_component_types():
    types = types_for_api_path("/resources/monitoring")
    assert "monitoring/appinsights" in types
    assert "monitoring/loganalytics" in types
    assert len(types) >= 2


def test_legacy_integration_aggregate_maps_to_component_types():
    types = types_for_api_path("/resources/integration")
    assert "integration/apim" in types
    assert "integration/datafactory" in types


def test_legacy_analytics_aggregate_maps_to_component_types():
    types = types_for_api_path("/resources/analytics")
    assert "analytics/synapse" in types
    assert "analytics/databricks" in types
