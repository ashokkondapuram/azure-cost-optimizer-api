"""Networking optimization sub-engines (Firewall/CDN and extended private link stack)."""
from __future__ import annotations

from typing import Any

from app.optimizer.resource_engines.runtime.base import ResourceSubEngine
from app.optimizer.resource_engines.networking.analysis import (
    analyze_cdn_profiles,
    analyze_firewalls,
    analyze_private_dns_zones,
    analyze_private_endpoints,
    analyze_private_link_services,
    analyze_vnets,
)


class NetworkingSubEngine(ResourceSubEngine):
    component = "Networking"
    bucket_keys = ("firewalls", "cdn_profiles")

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        firewalls = self.prepare_resources(buckets.get("firewalls") or [])
        cdn = self.prepare_resources(buckets.get("cdn_profiles") or [])
        findings = analyze_firewalls(self.engine, self.ctx.subscription_id, firewalls, self.ctx.cost_by_resource)
        findings.extend(analyze_cdn_profiles(self.engine, self.ctx.subscription_id, cdn, self.ctx.cost_by_resource))
        return self.enhance_findings(findings, firewalls + cdn)


class NetworkingExtendedSubEngine(ResourceSubEngine):
    component = "Networking Extended"
    bucket_keys = (
        "vnets",
        "private_endpoints",
        "private_link_services",
        "private_dns_zones",
    )

    def analyze(self, buckets: dict[str, list]) -> list[Any]:
        vnets = self.prepare_resources(buckets.get("vnets") or [])
        private_endpoints = self.prepare_resources(buckets.get("private_endpoints") or [])
        private_link_services = self.prepare_resources(buckets.get("private_link_services") or [])
        private_dns_zones = self.prepare_resources(buckets.get("private_dns_zones") or [])
        findings = analyze_vnets(self.engine, self.ctx.subscription_id, vnets, self.ctx.cost_by_resource)
        findings.extend(
            analyze_private_endpoints(
                self.engine, self.ctx.subscription_id, private_endpoints, self.ctx.cost_by_resource,
            ),
        )
        findings.extend(
            analyze_private_link_services(
                self.engine, self.ctx.subscription_id, private_link_services, self.ctx.cost_by_resource,
            ),
        )
        findings.extend(
            analyze_private_dns_zones(
                self.engine, self.ctx.subscription_id, private_dns_zones, self.ctx.cost_by_resource,
            ),
        )
        return self.enhance_findings(
            findings,
            vnets + private_endpoints + private_link_services + private_dns_zones,
        )
