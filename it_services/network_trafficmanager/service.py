"""IT service entity — public exports for Traffic Manager profile."""

from __future__ import annotations

SERVICE_ID = "network-trafficmanager"
CANONICAL_TYPE = "network/trafficmanager"
ARM_TYPE = "Microsoft.Network/trafficManagerProfiles"
DISPLAY_NAME = "Traffic Manager profile"
API_SLUG = "trafficmanager"
COMPONENT = "None"

from it_services.network_trafficmanager.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC


SubEngine = None  # profile-only service
