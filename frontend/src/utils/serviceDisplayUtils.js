/** Shared human-readable metric formatting for all IT services (mirrors app/service_display.py). */

import { formatFactValue } from './resourceMetricsUtils';
// Canonical source: data/service_display_defaults.json (synced via scripts/sync-service-display-defaults.js)
import serviceDisplayDefaults from '../data/service_display_defaults.json';

export const MISSING_DISPLAY = 'Not synced';
export const INVENTORY_MISSING_DISPLAY = 'Not in inventory sync';
export const EMPTY_PROPERTY_DISPLAY = '—';

const PROPERTY_LABELS = serviceDisplayDefaults?.property_labels || {};

const ZERO_VALUE_LABELS = {
  avg_cpu_pct: '0% CPU',
  cpu_pct: '0% CPU',
  cluster_cpu_pct: '0% cluster CPU',
  avg_memory_pct: '0% memory',
  avg_mem_pct: '0% memory',
  memory_usage_pct: '0% memory',
  cluster_mem_pct: '0% cluster memory',
  storage_pct: '0% utilization',
  disk_iops_utilization_pct: '0% IOPS utilization',
  disk_throughput_utilization_pct: '0% throughput utilization',
  used_capacity_bytes: '0 GB used',
  egress_bytes: '0 GB egress',
  byte_count: '0 GB',
  transaction_count: '0 transactions',
  request_count: '0 requests',
  api_hits: '0 API calls',
  node_count: '0 nodes',
  idle_nodes: '0 idle nodes',
  size_gb: '0 GB',
};

const RULE_PREFIX_CANONICAL = [
  ['STORAGE_', 'storage/account'],
  ['DISK_', 'compute/disk'],
  ['SNAPSHOT_', 'compute/snapshot'],
  ['VMSS_', 'compute/vmss'],
  ['VM_', 'compute/vm'],
  ['AKS_', 'containers/aks'],
  ['ACR_', 'containers/acr'],
  ['COSMOS_', 'database/cosmosdb'],
  ['POSTGRESQL_', 'database/postgresql'],
  ['REDIS_', 'database/redis'],
  ['SQL_', 'database/sql'],
  ['LOAD_BALANCER_', 'network/loadbalancer'],
  ['NAT_GATEWAY_', 'network/nat'],
  ['APP_GATEWAY_', 'network/appgateway'],
  ['PUBLIC_IP_', 'network/publicip'],
  ['KEYVAULT_', 'security/keyvault'],
];

export function resolveCanonicalType(resourceType = '', ruleId = '') {
  const rtype = String(resourceType || '').trim().toLowerCase();
  if (rtype.includes('/')) return rtype;
  const rid = String(ruleId || '').toUpperCase();
  for (const [prefix, canonical] of RULE_PREFIX_CANONICAL) {
    if (rid.startsWith(prefix)) return canonical;
  }
  return rtype || 'generic';
}

function zeroLabel(factKey) {
  const key = String(factKey || '').toLowerCase();
  for (const [zk, label] of Object.entries(ZERO_VALUE_LABELS)) {
    if (zk.toLowerCase() === key) return label;
  }
  return null;
}

/** Format metric — null/undefined is missing; 0 uses explicit zero label when configured. */
export function formatServiceFact(factKey, value, unit) {
  if (value == null || value === '') return MISSING_DISPLAY;
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  const num = Number(value);
  if (Number.isFinite(num) && num === 0) {
    const zero = zeroLabel(factKey);
    if (zero) return zero;
  }
  return formatFactValue(factKey, value, unit);
}

export function formatEvidenceCheckValue(check) {
  if (check?.value_display != null && check.value_display !== '') return check.value_display;
  if (check?.value == null || check?.value === '') return MISSING_DISPLAY;
  if (check?.fact_key) return formatServiceFact(check.fact_key, check.value);
  return String(check.value);
}

export function formatEvidenceThreshold(check) {
  if (check?.threshold_display != null && check.threshold_display !== '') return check.threshold_display;
  return check?.threshold ?? '—';
}

/** Lookup configured label for a property path or leaf key. */
export function resolvePropertyLabel(key) {
  const normalized = String(key || '').trim();
  if (!normalized) return 'Property';
  const leaf = normalized.split('.').pop() || normalized;
  const lower = normalized.toLowerCase();
  const leafLower = leaf.toLowerCase();
  for (const [candidate, label] of Object.entries(PROPERTY_LABELS)) {
    if (candidate.toLowerCase() === lower || candidate.toLowerCase() === leafLower) {
      return label;
    }
  }
  return null;
}
