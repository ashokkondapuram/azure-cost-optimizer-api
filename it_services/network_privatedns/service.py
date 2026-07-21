"""IT service entity — public exports for Private DNS zone."""

from __future__ import annotations

SERVICE_ID = "network-privatedns"
CANONICAL_TYPE = "network/privatedns"
ARM_TYPE = "Microsoft.Network/privateDnsZones"
DISPLAY_NAME = "Private DNS zone"
API_SLUG = "privatedns"
COMPONENT = "Networking Extended"

from it_services.network_privatedns.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.network_privatedns.engine.sub_engine import PrivateDnsSubEngine as SubEngine

