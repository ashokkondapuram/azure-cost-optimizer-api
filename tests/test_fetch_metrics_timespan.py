"""Tests for timespan coercion inside fetch_metrics_for_resource."""

from unittest.mock import MagicMock, patch

from app.metrics_api import fetch_metrics_for_resource

VM_RID = (
    "/subscriptions/aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/resourceGroups/rg/providers/"
    "Microsoft.Compute/virtualMachines/vm1"
)


def test_fetch_metrics_for_resource_coerces_object_shaped_timespan():
    profile = MagicMock()
    profile.metrics = [MagicMock(timespan="P7D")]
    profile.metric_names.return_value = ["Percentage CPU"]
    profile.aggregations.return_value = "Average"
    profile.canonical_type = "compute/vm"

    client = MagicMock()
    client.get_resource_metrics.return_value = {"value": []}

    with patch("app.metrics_api.get_monitor_profile", return_value=profile), patch(
        "app.azure_resources.AzureResourcesClient",
        return_value=client,
    ), patch("app.auth.arm_auth_context"), patch(
        "app.auth.get_token",
        return_value="token",
    ), patch(
        "app.metrics_api.build_metrics_detail",
        return_value=[],
    ), patch(
        "app.monitor_metrics.enrich_derived_monitor_facts",
        return_value={},
    ), patch(
        "app.metrics_api._shape_unified_response",
        return_value={"ok": True, "metrics": [], "derived": []},
    ) as shape_mock:
        result = fetch_metrics_for_resource(
            VM_RID,
            timespan={"value": "P14D", "label": "Last 14 days"},
            db=None,
        )

    assert result["ok"] is True
    client.get_resource_metrics.assert_called_once()
    assert client.get_resource_metrics.call_args.kwargs["timespan"] == "P14D"
    shape_mock.assert_called_once()
    assert shape_mock.call_args.kwargs["timespan"] == "P14D"
