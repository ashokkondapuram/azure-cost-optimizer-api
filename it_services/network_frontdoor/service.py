"""IT service entity — public exports for Azure Front Door."""

from __future__ import annotations

SERVICE_ID = "network-frontdoor"
CANONICAL_TYPE = "network/frontdoor"
ARM_TYPE = "Microsoft.Network/frontdoors"
DISPLAY_NAME = "Azure Front Door"
API_SLUG = "frontdoor"
COMPONENT = "None"

from it_services.network_frontdoor.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC


SubEngine = None  # profile-only service
