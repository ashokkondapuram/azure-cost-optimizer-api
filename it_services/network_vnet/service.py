"""IT service entity — public exports for Virtual network."""

from __future__ import annotations

SERVICE_ID = "network-vnet"
CANONICAL_TYPE = "network/vnet"
ARM_TYPE = "Microsoft.Network/virtualNetworks"
DISPLAY_NAME = "Virtual network"
API_SLUG = "vnets"
COMPONENT = "Networking Extended"

from it_services.network_vnet.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.network_vnet.engine.sub_engine import VnetSubEngine as SubEngine

