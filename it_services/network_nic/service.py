"""IT service entity — public exports for Network interface."""

from __future__ import annotations

SERVICE_ID = "network-nic"
CANONICAL_TYPE = "network/nic"
ARM_TYPE = "Microsoft.Network/networkInterfaces"
DISPLAY_NAME = "Network interface"
API_SLUG = "nics"
COMPONENT = "Network Interfaces"

from it_services.network_nic.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.network_nic.engine.sub_engine import NicSubEngine as SubEngine

