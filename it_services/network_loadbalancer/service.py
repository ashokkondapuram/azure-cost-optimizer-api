"""IT service entity — public exports for Load balancer."""

from __future__ import annotations

SERVICE_ID = "network-loadbalancer"
CANONICAL_TYPE = "network/loadbalancer"
ARM_TYPE = "Microsoft.Network/loadBalancers"
DISPLAY_NAME = "Load balancer"
API_SLUG = "loadbalancers"
COMPONENT = "Load Balancers"

from it_services.network_loadbalancer.resource_profile import MONITOR_PROFILE, TECHNICAL_FETCH_SPEC

from it_services.network_loadbalancer.engine.sub_engine import LoadBalancerSubEngine as SubEngine

