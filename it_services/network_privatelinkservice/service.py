"""IT service entity — public exports for Private link service."""

from __future__ import annotations

SERVICE_ID = "network-privatelinkservice"
CANONICAL_TYPE = "network/privatelinkservice"
ARM_TYPE = "Microsoft.Network/privateLinkServices"
DISPLAY_NAME = "Private link service"
API_SLUG = "privatelinkservices"
COMPONENT = "Networking Extended"

from it_services.network_privatelinkservice.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.network_privatelinkservice.engine.sub_engine import PrivateLinkServiceSubEngine as SubEngine

