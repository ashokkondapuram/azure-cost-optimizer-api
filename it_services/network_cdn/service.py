"""IT service entity — public exports for CDN profile."""

from __future__ import annotations

SERVICE_ID = "network-cdn"
CANONICAL_TYPE = "network/cdn"
ARM_TYPE = "Microsoft.Cdn/profiles"
DISPLAY_NAME = "CDN profile"
API_SLUG = "cdn"
COMPONENT = "Networking"

from it_services.network_cdn.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.network_cdn.engine.sub_engine import CdnSubEngine as SubEngine

