"""Tests for Application Gateway listener detection."""

from app.appgateway_utils import (
    application_gateway_has_listeners,
    application_gateway_listener_details,
    http_listener_count,
)
from app.arm_resource_enrichment import enrich_arm_resources_for_type


class _FakeAgwClient:
    def get_application_gateway(self, subscription_id, resource_group, gateway_name):
        return {
            "id": (
                f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
                f"/providers/Microsoft.Network/applicationGateways/{gateway_name}"
            ),
            "name": gateway_name,
            "properties": {
                "httpListeners": [
                    {"name": "listener-https", "protocol": "Https"},
                    {"name": "listener-http", "protocol": "Http"},
                ],
                "provisioningState": "Succeeded",
            },
        }

    def get_arm_resource(self, resource_id: str, *, api_version=None):
        return self.get_application_gateway("", "", "")


def test_http_listener_count_from_properties():
    props = {"httpListeners": [{"name": "l1"}, {"name": "l2"}]}
    assert http_listener_count(props) == 2
    assert application_gateway_has_listeners(props) is True


def test_http_listener_count_missing_returns_zero():
    assert http_listener_count({}) == 0
    assert http_listener_count({"httpListeners": []}) == 0


def test_http_listener_count_from_routing_rules():
    props = {
        "httpListeners": [],
        "requestRoutingRules": [
            {
                "name": "rule1",
                "properties": {
                    "httpListener": {
                        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/applicationGateways/agw/httpListeners/l1",
                    },
                },
            },
            {
                "name": "rule2",
                "properties": {
                    "httpListener": {
                        "id": "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Network/applicationGateways/agw/httpListeners/l1",
                    },
                },
            },
        ],
    }
    assert http_listener_count(props) == 1


def test_application_gateway_listener_details():
    props = {
        "httpListeners": [
            {"name": "https-listener", "properties": {"protocol": "Https"}},
            {"name": "http-listener", "properties": {"protocol": "Http"}},
        ],
    }
    details = application_gateway_listener_details(props)
    assert len(details) == 2
    assert details[0]["protocol"] == "Https"


def test_enrich_application_gateways_fetches_when_list_omits_listeners():
    thin = {
        "id": "/subscriptions/sub/resourceGroups/rg-net/providers/Microsoft.Network/applicationGateways/prod-agw",
        "name": "prod-agw",
        "properties": {"provisioningState": "Succeeded"},
    }
    enriched = enrich_arm_resources_for_type(_FakeAgwClient(), "sub", [thin], "network/appgateway")
    assert len(enriched) == 1
    assert http_listener_count(enriched[0].get("properties")) == 2


def test_enrich_skips_get_when_listeners_present():
    class _FailClient:
        def get_application_gateway(self, *args, **kwargs):
            raise AssertionError("GET should not be called when list has listeners")

        def get_arm_resource(self, *args, **kwargs):
            raise AssertionError("GET should not be called when list has listeners")

    full = {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/applicationGateways/agw1",
        "name": "agw1",
        "properties": {"httpListeners": [{"name": "only"}]},
    }
    enriched = enrich_arm_resources_for_type(_FailClient(), "sub", [full], "network/appgateway")
    assert http_listener_count(enriched[0]["properties"]) == 1
