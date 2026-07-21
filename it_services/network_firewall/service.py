"""IT service entity — public exports for Azure Firewall."""

from __future__ import annotations

SERVICE_ID = "network-firewall"
CANONICAL_TYPE = "network/firewall"
ARM_TYPE = "Microsoft.Network/azureFirewalls"
DISPLAY_NAME = "Azure Firewall"
API_SLUG = "firewall"
COMPONENT = "Networking"

from it_services.network_firewall.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.network_firewall.engine.sub_engine import FirewallSubEngine as SubEngine

