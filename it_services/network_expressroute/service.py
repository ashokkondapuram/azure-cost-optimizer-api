"""IT service entity — public exports for ExpressRoute circuit."""

from __future__ import annotations

SERVICE_ID = "network-expressroute"
CANONICAL_TYPE = "network/expressroute"
ARM_TYPE = "Microsoft.Network/expressRouteCircuits"
DISPLAY_NAME = "ExpressRoute circuit"
API_SLUG = "expressroute"
COMPONENT = "None"

from it_services.network_expressroute.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC


SubEngine = None  # profile-only service
