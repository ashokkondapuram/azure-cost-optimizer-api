"""IT service entity — public exports for NAT gateway."""

from __future__ import annotations

SERVICE_ID = "network-nat"
CANONICAL_TYPE = "network/nat"
ARM_TYPE = "Microsoft.Network/natGateways"
DISPLAY_NAME = "NAT gateway"
API_SLUG = "natgateways"
COMPONENT = "NAT Gateways"

from it_services.network_nat.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.network_nat.engine.sub_engine import NatSubEngine as SubEngine

