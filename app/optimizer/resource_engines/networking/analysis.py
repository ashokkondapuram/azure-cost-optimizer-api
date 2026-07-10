"""Compatibility aggregate — functions moved to it_services."""
from it_services.network_firewall.engine.analysis import analyze_firewalls
from it_services.network_cdn.engine.analysis import analyze_cdn_profiles
from it_services.network_vnet.engine.analysis import analyze_vnets
from it_services.network_privateendpoint.engine.analysis import analyze_private_endpoints
from it_services.network_privatelinkservice.engine.analysis import analyze_private_link_services
from it_services.network_privatedns.engine.analysis import analyze_private_dns_zones

__all__ = ['analyze_firewalls', 'analyze_cdn_profiles', 'analyze_vnets', 'analyze_private_endpoints', 'analyze_private_link_services', 'analyze_private_dns_zones']
