"""IT service entity — public exports for Network security group."""

from __future__ import annotations

SERVICE_ID = "network-nsg"
CANONICAL_TYPE = "network/nsg"
ARM_TYPE = "Microsoft.Network/networkSecurityGroups"
DISPLAY_NAME = "Network security group"
API_SLUG = "nsgs"
COMPONENT = "Network Security Groups"

from it_services.network_nsg.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.network_nsg.engine.sub_engine import NsgSubEngine as SubEngine

