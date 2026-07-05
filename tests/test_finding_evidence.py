"""Tests for finding evidence enrichment and resource links."""

from app.finding_evidence import (
    app_route_for_resource,
    azure_portal_url,
    enrich_evidence,
    enrich_finding_for_api,
)


def test_app_gateway_idle_evidence():
    finding = {
        "rule_id": "APPGW_UNUSED",
        "resource_name": "prod-agw",
        "detail": "Application Gateway has no HTTP listeners.",
        "estimated_savings_usd": 120.5,
        "evidence": {"http_listener_count": 0, "monthly_cost_usd": 120.5, "determination": "idle_no_listeners"},
    }
    out = enrich_evidence("APPGW_UNUSED", finding["evidence"], finding)
    assert out["determination"] == "idle_no_listeners"
    assert out["data_source"] == "synced_inventory"
    assert out["http_listener_count"] == 0
    assert out.get("checks")
    assert out["checks"][0]["signal"] == "HTTP listeners configured"
    assert "no HTTP listeners" in out["summary"]
    assert out["savings_methodology"]["method"] == "full_monthly_cost"
    assert "http_listener_count" not in out["resource_details"]
    perf_ids = {m["id"] for m in out["optimization_metrics"]["performance"]}
    assert "http_listeners" in perf_ids
    assert out["optimization_metrics"]["data_quality"] == "inventory_and_cost"
    assert "monthly_cost_usd" not in out["resource_details"]


def test_app_gateway_low_throughput_evidence():
    finding = {
        "rule_id": "APP_GATEWAY_IDLE_EXTENDED",
        "resource_name": "prod-agw",
        "detail": "Application Gateway has listeners but very low throughput in Azure Monitor.",
        "estimated_savings_usd": 50.0,
        "resource_type": "network/appgateway",
        "evidence": {
            "determination": "low_throughput",
            "data_source": "azure_monitor",
            "http_listener_count": 2,
            "throughput_bytes": 120.0,
            "request_count": 45.0,
            "monthly_cost_usd": 125.0,
        },
    }
    out = enrich_evidence("APP_GATEWAY_IDLE_EXTENDED", finding["evidence"], finding)
    assert out["determination"] == "low_throughput"
    assert out["data_source"] == "azure_monitor"
    assert "low throughput" in out["summary"].lower()
    assert out["savings_methodology"]["method"] == "factor_of_monthly_cost"
    assert out["optimization_metrics"]["data_quality"] == "azure_monitor_and_cost"


def test_resource_details_exclude_cost_and_performance_fields():
    out = enrich_evidence(
        "VM_IDLE",
        {"avg_cpu_pct": 2.1, "vm_size": "Standard_D2s_v3", "monthly_cost_usd": 88.0},
        {"estimated_savings_usd": 79.0},
    )
    details = out["resource_details"]
    assert "avg_cpu_pct" not in details
    assert "vm_size" not in details
    assert "monthly_cost_usd" not in details
    assert "savings_factor" not in details
    perf_ids = {m["id"] for m in out["optimization_metrics"]["performance"]}
    assert "avg_cpu" in perf_ids
    assert "vm_size" in perf_ids


def test_load_balancer_idle_evidence():
    evidence = {"backend_pool_count": 2, "all_backends_empty": True}
    out = enrich_evidence("LB_NO_BACKEND", evidence, {})
    assert out["determination"] == "lb_idle_no_backends"
    assert out.get("checks")
    assert out["checks"][0]["signal"] == "Backend pools with targets"
    assert "2 pool" in out["summary"]


def test_enrich_finding_adds_resource_links():
    rid = (
        "/subscriptions/abc123/resourceGroups/rg-net/providers/"
        "Microsoft.Network/applicationGateways/my-agw"
    )
    finding = enrich_finding_for_api({
        "rule_id": "APP_GATEWAY_IDLE_EXTENDED",
        "resource_id": rid,
        "resource_name": "my-agw",
        "resource_type": "Microsoft.Network/applicationGateways",
        "evidence": {"http_listener_count": 0},
    })
    assert finding["resource_app_path"] == "/appgateways"
    assert finding["resource_app_href"] == "/appgateways?search=my-agw"
    assert finding["azure_portal_url"].startswith("https://portal.azure.com/#resource")
    assert "my-agw" in finding["azure_portal_url"] or "applicationGateways" in finding["azure_portal_url"]


def test_app_route_for_canonical_type():
    assert app_route_for_resource("network/appgateway", "") == "/appgateways"
    assert app_route_for_resource("monitoring/loganalytics", "") == "/loganalytics"


def test_azure_portal_url_requires_arm_id():
    assert azure_portal_url("") is None
    assert azure_portal_url("not-an-arm-id") is None
    url = azure_portal_url("/subscriptions/x/resourceGroups/y/providers/Microsoft.Compute/virtualMachines/vm1")
    assert url is not None
    assert "portal.azure.com" in url
