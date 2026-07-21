"""IT service entity — public exports for Application gateway."""

from __future__ import annotations

SERVICE_ID = "network-appgateway"
CANONICAL_TYPE = "network/appgateway"
ARM_TYPE = "Microsoft.Network/applicationGateways"
DISPLAY_NAME = "Application gateway"
API_SLUG = "appgateways"
COMPONENT = "Application Gateways"

from it_services.network_appgateway.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.network_appgateway.engine.sub_engine import AppGatewaySubEngine as SubEngine

