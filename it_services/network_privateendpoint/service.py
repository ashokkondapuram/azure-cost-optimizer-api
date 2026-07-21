"""IT service entity — public exports for Private endpoint."""

from __future__ import annotations

SERVICE_ID = "network-privateendpoint"
CANONICAL_TYPE = "network/privateendpoint"
ARM_TYPE = "Microsoft.Network/privateEndpoints"
DISPLAY_NAME = "Private endpoint"
API_SLUG = "privateendpoints"
COMPONENT = "Networking Extended"

from it_services.network_privateendpoint.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.network_privateendpoint.engine.sub_engine import PrivateEndpointSubEngine as SubEngine

