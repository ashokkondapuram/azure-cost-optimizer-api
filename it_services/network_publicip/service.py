"""IT service entity — public exports for Public IP address."""

from __future__ import annotations

SERVICE_ID = "network-publicip"
CANONICAL_TYPE = "network/publicip"
ARM_TYPE = "Microsoft.Network/publicIPAddresses"
DISPLAY_NAME = "Public IP address"
API_SLUG = "publicips"
COMPONENT = "Public IPs"

from it_services.network_publicip.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.network_publicip.engine.sub_engine import PublicIpSubEngine as SubEngine

