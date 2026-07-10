# Azure Networking Resource Optimization (9 resources)

**Status:** Approved  
**Date:** Jul 7, 2026  
**Author:** Platform team  

## Problem statement

Networking optimization today is mostly **idle/orphan detection** with limited Azure Monitor integration. Public IPs, NAT Gateways, Load Balancers, and Application Gateways have partial metric hooks; VNets, NSGs, Private Endpoints, Private Link Services, and Private DNS rely on inventory heuristics or cost-export rules.

Gaps:

- No **pricing / cost-model catalogs** per networking SKU (hourly, CU, data transfer, flow logs).
- Missing **throughput, SNAT, CU, and connection** metrics on several resource types.
- No **rightsizing, consolidation, or regional pricing** recommendations comparable to Redis/PostgreSQL/Cosmos engines.
- Findings are not consistently ranked by **action priority (P1–P3)** across networking rules.

## Proposed solution

Enhance all **9 networking resource types** using the same pipeline as database engines:

```
load_azure_monitor_metrics()
  → extract_monitor_facts_from_profile()
  → enrich_derived_monitor_facts()
  → resource_facts on inventory rows
  → optimization_rules evaluators
  → ExtendedFinding (priority, evidence, retail savings)
```

### Resources in scope

| # | Resource | Canonical type | Primary cost driver |
|---|----------|----------------|---------------------|
| 1 | Public IPs | `network/publicip` | Hourly per assigned IP |
| 2 | Virtual Networks | `network/vnet` | Integrated services (NAT, VPN, ER) |
| 3 | NAT Gateways | `network/nat` | Hourly + per-IP SNAT |
| 4 | Load Balancers | `network/loadbalancer` | Data processed (GB) |
| 5 | Application Gateways | `network/appgateway` | Capacity Units (CU) |
| 6 | Network Security Groups | `network/nsg` | Flow log ingestion + storage |
| 7 | Private Endpoints | `network/privateendpoint` | Hourly + data transfer |
| 8 | Private Link Services | `network/privatelinkservice` | Hourly + NAT/data processing |
| 9 | Private DNS Zones | `network/privatedns` | Zone fee + queries |

### Implementation phases

| Phase | Deliverable |
|-------|-------------|
| **1 — Spec** | This document; team review → `specs/approved/` |
| **2 — Data** | 9 JSON catalogs (thresholds + pricing); catalog loaders (`*_catalog.py`) |
| **3 — Rules** | `optimization_rules.py` per resource; refactor `analysis.py` orchestrators |
| **4 — Integration** | `rule_catalog.py`, `advanced_rules.py`, `rule_evidence_specs.py`, `metrics_triggers.py`, MONITOR_PROFILE expansions |
| **5 — Pricing** | `azure_retail_pricing.py` helpers; regional multipliers; savings estimates |
| **6 — UI / Hub** | Waste heatmap + Optimization hub surfacing for idle network rules; priority-sorted actions |

## Design decisions (confirmed)

| Decision | Choice |
|----------|--------|
| Work type | **Production** — spec before merge |
| Metrics | **Live Azure Monitor** at analysis time |
| Pricing | **Azure Retail Prices API** + regional multipliers |
| Finding rank | **Effort / priority first** (P1 → P3), then savings within tier |
| Automation | **Advisory only** — no auto-delete or auto-resize |

### Priority mapping (networking)

| Priority | When to use | Examples |
|----------|-------------|----------|
| **P1** | Reliability / security / imminent cost spike | SNAT exhaustion, App GW CU > 80%, DDoS on idle IP, throttling risk |
| **P2** | Clear savings, moderate effort | Unassociated public IP, idle NAT GW, unused private endpoint, Basic SKU migration |
| **P3** | Governance / hygiene / small $ | NSG rule cleanup, DNS zone consolidation, flow log retention |

## Data model changes

None. Reuse `optimization_findings` extended fields (`evidence_json`, `action_priority`, `estimated_savings_usd`, etc.).

### New data files (`data/`)

| File | Purpose |
|------|---------|
| `public_ip_metrics_thresholds.json` | Idle byte/packet thresholds, Basic SKU sunset |
| `vnet_service_costs.json` | NAT/VPN/ER/endpoint reference costs |
| `nat_gateway_metrics_thresholds.json` | SNAT limits, connection thresholds |
| `load_balancer_metrics_thresholds.json` | Throughput, SNAT %, health probe defaults |
| `app_gateway_metrics_thresholds.json` | CU targets, autoscale bands |
| `nsg_flow_log_costs.json` | Flow log $/GB, retention guidance |
| `private_endpoint_cost_model.json` | Hourly + regional data transfer |
| `private_link_service_cost_model.json` | Hourly + NAT port limits |
| `private_dns_zone_cost_model.json` | Zone fee + query rates |

### New catalog loaders (`app/`)

- `public_ip_catalog.py`, `vnet_catalog.py`, `nat_gateway_catalog.py`, `load_balancer_catalog.py`, `app_gateway_catalog.py`, `nsg_catalog.py`, `private_endpoint_catalog.py`, `private_link_service_catalog.py`, `private_dns_catalog.py`

Pattern: mirror `redis_sku_catalog.py` / `cosmosdb_catalog.py`.

## API changes

No new endpoints. Findings surface via existing:

- `POST /optimize/analyze`
- `GET /optimize/findings`
- `GET /idle-resources/sweep/{subscription_id}` (idle/waste rules only)

## UI changes

- Optimization hub Actions tab: network findings sorted by **P1 → P3**, then savings.
- Waste heatmap: existing idle network rules (`PUBLIC_IP_*`, `NAT_GATEWAY_*`, etc.) — no rightsize rules on heatmap.
- Resource inventory pages: evidence panels for new metric-driven rules.

## Per-resource rules (summary)

### 1. Public IPs

| Rule ID | Trigger | Priority |
|---------|---------|----------|
| `PUBLIC_IP_UNASSOCIATED_EXTENDED` | Static, no association 30d | P2 |
| `PUBLIC_IP_IDLE_TRAFFIC_EXTENDED` | ByteCount < threshold 7d (enhance existing) | P2 |
| `PUBLIC_IP_BASIC_SKU_MIGRATION` | Basic SKU before Sept 2025 sunset | P2 |
| `PUBLIC_IP_REGIONAL_COST_REVIEW` | Non-prod in premium region | P3 |

**Metrics:** ByteCount, PacketCount, IfUnderDDoSAttack, VipAvailability

### 2. Virtual Networks

| Rule ID | Trigger | Priority |
|---------|---------|----------|
| `VNET_UNUSED_SUBNET_EXTENDED` | Empty subnet address space | P3 |
| `VNET_PEERING_CONSOLIDATION_EXTENDED` | Low-traffic / redundant peering | P2 |
| `VNET_NAT_GATEWAY_REVIEW` | NAT on multiple VNets → consolidate | P2 |
| `VNET_IDLE_GATEWAY_EXTENDED` | VPN/ER gateway idle hourly spend | P2 |

**Metrics:** PingMesh*, BytesDroppedDDoS; cost attribution from child resources

### 3. NAT Gateways

| Rule ID | Trigger | Priority |
|---------|---------|----------|
| `NAT_GATEWAY_SNAT_EXHAUSTION` | SNATConnectionCount > 80% capacity | P1 |
| `NAT_GATEWAY_IDLE_EXTENDED` | (enhance existing) | P2 |
| `NAT_GATEWAY_SKU_V2_UPGRADE` | Throughput > 40 Gbps or IPv6 need | P2 |
| `NAT_GATEWAY_SUBNET_CONSOLIDATION` | Share gateway across subnets | P2 |

**Metrics:** SNATConnectionCount, ByteCount, DatapathAvailability, PacketDropCount

### 4. Load Balancers

| Rule ID | Trigger | Priority |
|---------|---------|----------|
| `LOAD_BALANCER_SNAT_PRESSURE` | SNATPortUsage > 70% | P1 |
| `LOAD_BALANCER_IDLE_EXTENDED` | (enhance existing) | P2 |
| `LOAD_BALANCER_THROUGHPUT_RIGHTSIZE` | ByteCount < 10% of 30d peak | P2 |
| `LOAD_BALANCER_BACKEND_CONSOLIDATION` | Empty / low-traffic pools | P2 |

**Metrics:** ByteCount, SNATPortUsage, UsedSnatPorts, DataPathAvailability, HealthProbeStatus

### 5. Application Gateways

| Rule ID | Trigger | Priority |
|---------|---------|----------|
| `APP_GATEWAY_CU_SATURATION` | EstimatedBilledCapacityUnits > 80% 7d | P1 |
| `APP_GATEWAY_CU_RIGHTSIZE_DOWN` | CU < 30% 30d | P2 |
| `APP_GATEWAY_AUTOSCALE_SCHEDULE` | Off-peak scale-to-zero candidate | P2 |
| `APP_GATEWAY_IDLE_EXTENDED` | (enhance existing) | P2 |
| `APP_GATEWAY_ROUTING_CLEANUP` | Unused listeners / rules | P3 |

**Metrics:** EstimatedBilledCapacityUnits, Throughput, CurrentConnections, CurrentComputeUnits, HealthyHostCount

### 6. Network Security Groups

| Rule ID | Trigger | Priority |
|---------|---------|----------|
| `NSG_ORPHANED_EXTENDED` | (existing) | P3 |
| `NSG_PERMISSIVE_EXTENDED` | (existing) | P1 |
| `NSG_FLOW_LOG_COST` | Flow logs enabled, zero traffic 90d | P2 |
| `NSG_UNUSED_RULE_EXTENDED` | Flow log shows never-matched rules | P3 |

**Note:** NSG Flow Logs retirement timeline (2027) documented in evidence.

### 7. Private Endpoints

| Rule ID | Trigger | Priority |
|---------|---------|----------|
| `PRIVATE_ENDPOINT_ORPHAN_EXTENDED` | (enhance existing) | P2 |
| `PRIVATE_ENDPOINT_UNDERUTILIZED` | PEBytesIn+Out < 100 GB/mo 60d | P2 |
| `PRIVATE_ENDPOINT_CONSOLIDATION` | Duplicate service endpoints per VNet | P2 |

**Metrics:** PEBytesIn, PEBytesOut, ConnectionCount (or platform equivalents)

### 8. Private Link Services

| Rule ID | Trigger | Priority |
|---------|---------|----------|
| `PRIVATE_LINK_UNUSED_EXTENDED` | (enhance existing) | P2 |
| `PRIVATE_LINK_NAT_PORT_PRESSURE` | PLSNatPortsUsage > 80% | P1 |
| `PRIVATE_LINK_NAT_RIGHTSIZE` | PLSNatPortsUsage < 30% 30d | P2 |

### 9. Private DNS Zones

| Rule ID | Trigger | Priority |
|---------|---------|----------|
| `PRIVATE_DNS_EMPTY_EXTENDED` | (enhance existing) | P3 |
| `PRIVATE_DNS_UNUSED_ZONE` | QueryVolume = 0 for 90d | P2 |
| `PRIVATE_DNS_ZONE_CONSOLIDATION` | Overlapping records across zones | P3 |

**Metrics:** QueryVolume, RecordSetCount, VirtualNetworkLinkCount

## Acceptance criteria

### Global

- [ ] All 9 resource types load metrics via expanded `MONITOR_PROFILE` at analysis time.
- [ ] Each resource has a JSON catalog + Python loader with documented thresholds.
- [ ] New rules registered in `rule_catalog.py`, `advanced_rules.py`, and `rule_evidence_specs.py`.
- [ ] Findings include `action_priority` (P1–P3), structured `evidence_json`, and retail-based `estimated_savings_usd` where applicable.
- [ ] Actions UI lists network findings **P1 first**, then P2, then P3; savings breaks ties within tier.
- [ ] Unit tests per resource (`tests/test_*_network_optimization.py`) with mocked monitor facts.
- [ ] Idle/waste rules appear on waste heatmap; rightsize rules do not.

### Per-resource (minimum one new metric-driven rule each)

- [ ] Public IP: traffic-idle + Basic SKU migration
- [ ] VNet: integrated service cost / peering review
- [ ] NAT Gateway: SNAT exhaustion
- [ ] Load Balancer: SNAT pressure
- [ ] App Gateway: CU saturation + rightsize down
- [ ] NSG: flow log cost attribution
- [ ] Private Endpoint: underutilized bytes
- [ ] Private Link Service: NAT port pressure
- [ ] Private DNS: unused zone (zero queries)

## Out of scope

- Auto-execution (delete, resize, migrate) — advisory only.
- Azure Firewall, Front Door, Traffic Manager, ExpressRoute circuits (separate specs).
- Container-level Cosmos-style dimension filtering for Private Link.
- Replacing NSG Flow Logs with VNet flow logs migration tooling (document only).
- Cross-subscription hub-spoke topology automation.

## Dependencies

- `app/monitor_metrics.py` — metric fetch + derived facts
- `app/azure_retail_pricing.py` — regional hourly / data transfer estimates
- `app/optimizer/resource_engines/network/*` — existing sub-engines
- `app/resources/network/*` — MONITOR_PROFILE definitions
- Optimization hub + waste heatmap wiring (completed Jul 7, 2026)

## Open questions

1. **VNet analysis depth:** Account-level only, or traverse peerings/NAT per subscription graph? (Default: subscription inventory + peering metadata.)
2. **Flow log cost:** Use Cost Management actuals when available, or catalog $/GB estimate? (Default: catalog estimate + optional MTD cost overlay.)
3. **Phased delivery:** Ship all 9 in one epic, or 3 PRs (Public IP + NAT + LB → App GW + PE + PLS → VNet + NSG + DNS)? (Recommend 3 PRs.)

## Implementation notes

- Reuse `RedisFindingDraft` / `_append_draft` orchestration pattern from database engines.
- Extend `is_idle_or_waste_rule()` only for decommission-class network rules; keep rightsize off waste heatmap.
- Basic SKU sunset (Public IP, Load Balancer): hard-code deadline `2025-09-30` in catalog with evidence link.
- Rank sort key: `(priority_order, -estimated_savings_usd)` where `priority_order = {P1:0, P2:1, P3:2}`.
