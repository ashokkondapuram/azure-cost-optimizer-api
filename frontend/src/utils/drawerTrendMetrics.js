import { syncTypesForApiPath } from './syncScope';

const ARM_FRAGMENT_TO_CANONICAL = [
  ['microsoft.compute/disks', 'compute/disk'],
  ['microsoft.compute/virtualmachines', 'compute/vm'],
  ['microsoft.compute/virtualmachinescalesets', 'compute/vmss'],
  ['microsoft.storage/storageaccounts', 'storage/account'],
  ['microsoft.servicebus', 'messaging/servicebus'],
  ['microsoft.eventhub', 'messaging/eventhub'],
  ['microsoft.documentdb', 'database/cosmosdb'],
  ['microsoft.cache/redis', 'database/redis'],
  ['microsoft.sql/servers', 'database/sql'],
  ['microsoft.dbforpostgresql', 'database/postgresql'],
  ['microsoft.web/sites', 'appservice/webapp'],
  ['microsoft.web/serverfarms', 'appservice/plan'],
  ['microsoft.containerservice/managedclusters', 'containers/aks'],
  ['microsoft.containerregistry/registries', 'containers/acr'],
  ['microsoft.network/applicationgateways', 'network/appgateway'],
  ['microsoft.network/loadbalancers', 'network/loadbalancer'],
];

/**
 * Trend summary + chart metrics per canonical type.
 * Aligned with backend MONITOR_PROFILE metrics and optimization rule triggers.
 */
export const TREND_SUMMARY_METRICS_BY_TYPE = {
  'compute/vm': [
    { factKey: 'avg_cpu_pct', label: 'Average CPU', unit: '%', analysisTrendKey: 'cpu_trend' },
    { factKey: 'avg_memory_pct', label: 'Average memory', unit: '%', analysisTrendKey: 'memory_trend' },
    { factKey: 'max_cpu_pct', label: 'Peak CPU', unit: '%', analysisTrendKey: 'cpu_trend' },
    { factKey: 'network_out_bytes', label: 'Network egress', unit: 'bytes_per_sec' },
  ],
  'compute/vmss': [
    { factKey: 'avg_cpu_pct', label: 'Average CPU', unit: '%', analysisTrendKey: 'cpu_trend' },
    { factKey: 'avg_memory_pct', label: 'Average memory', unit: '%', analysisTrendKey: 'memory_trend' },
    { factKey: 'max_cpu_pct', label: 'Peak CPU', unit: '%', analysisTrendKey: 'cpu_trend' },
  ],
  'compute/disk': [
    { factKey: 'disk_read_iops', label: 'Read IOPS', unit: '' },
    { factKey: 'disk_write_iops', label: 'Write IOPS', unit: '' },
    { factKey: 'disk_read_bps', label: 'Read throughput', unit: 'bytes_per_sec' },
    { factKey: 'disk_write_bps', label: 'Write throughput', unit: 'bytes_per_sec' },
    { factKey: 'disk_iops_utilization_pct', label: 'IOPS utilization', unit: '%' },
    { factKey: 'disk_throughput_utilization_pct', label: 'Throughput utilization', unit: '%' },
    { factKey: 'disk_queue_depth', label: 'Queue depth', unit: '' },
    { factKey: 'disk_used_pct', label: 'Capacity used', unit: '%' },
  ],
  'storage/account': [
    { factKey: 'transaction_count', label: 'Transactions', unit: '' },
    { factKey: 'ingress_bytes', label: 'Data ingress', unit: 'bytes' },
    { factKey: 'egress_bytes', label: 'Data egress', unit: 'bytes' },
    { factKey: 'availability_pct', label: 'Availability', unit: '%' },
    { factKey: 'used_capacity_bytes', label: 'Capacity used', unit: 'bytes' },
  ],
  'network/appgateway': [
    { factKey: 'healthy_host_count', label: 'Healthy backend hosts', unit: '' },
    { factKey: 'throughput_bytes', label: 'Throughput', unit: 'bytes_per_sec' },
    { factKey: 'failed_request_count', label: 'Failed requests', unit: '' },
    { factKey: 'request_count', label: 'Total requests', unit: '' },
  ],
  'network/loadbalancer': [
    { factKey: 'backend_availability_pct', label: 'Backend availability', unit: '%' },
    { factKey: 'byte_count', label: 'Traffic volume', unit: 'bytes' },
    { factKey: 'used_snat_ports', label: 'Used SNAT ports', unit: '' },
  ],
  'containers/aks': [
    { factKey: 'cluster_cpu_pct', label: 'Cluster CPU', unit: '%' },
    { factKey: 'cluster_mem_pct', label: 'Cluster memory', unit: '%' },
    { factKey: 'pod_count', label: 'Ready pods', unit: 'count' },
  ],
  'database/postgresql': [
    { factKey: 'cpu_pct', label: 'CPU utilization', unit: '%' },
    { factKey: 'memory_pct', label: 'Memory utilization', unit: '%' },
    { factKey: 'storage_pct', label: 'Storage utilization', unit: '%' },
    { factKey: 'active_connections', label: 'Active connections', unit: '' },
  ],
  'database/sql': [],
  'appservice/webapp': [
    { factKey: 'request_count', label: 'HTTP requests', unit: '' },
    { factKey: 'cpu_time_sec', label: 'CPU time', unit: 'sec' },
    { factKey: 'avg_memory_bytes', label: 'Memory working set', unit: 'bytes' },
  ],
  'appservice/plan': [
    { factKey: 'cpu_pct', label: 'Plan CPU', unit: '%' },
    { factKey: 'memory_pct', label: 'Plan memory', unit: '%' },
  ],
  'messaging/servicebus': [
    { factKey: 'active_messages', label: 'Active messages', unit: '' },
    { factKey: 'incoming_requests', label: 'Incoming requests', unit: '' },
    { factKey: 'outgoing_messages', label: 'Outgoing messages', unit: '' },
  ],
  'messaging/eventhub': [
    { factKey: 'incoming_messages', label: 'Incoming events', unit: '' },
    { factKey: 'outgoing_messages', label: 'Outgoing events', unit: '' },
  ],
  'database/cosmosdb': [
    { factKey: 'normalized_ru_pct', label: 'RU utilization', unit: '%' },
    { factKey: 'normalized_ru_peak_pct', label: 'Peak RU', unit: '%' },
    { factKey: 'total_ru', label: 'Total RU consumed', unit: '' },
    { factKey: 'provisioned_throughput', label: 'Provisioned throughput', unit: '' },
    { factKey: 'data_usage_bytes', label: 'Data usage', unit: 'bytes' },
  ],
  'database/redis': [
    { factKey: 'memory_pct', label: 'Memory used', unit: '%' },
    { factKey: 'server_load_pct', label: 'Server load', unit: '%' },
    { factKey: 'ops_per_sec', label: 'Operations/sec', unit: '' },
  ],
};

/** Primary utilization metrics for Trends tab charts, keyed by resource kind. */
const TREND_METRIC_PROFILES = [
  {
    test: (key) => key.includes('compute/disk')
      || key.includes('microsoft.compute/disks')
      || (key.includes('disk') && !key.includes('snapshot')),
    metrics: TREND_SUMMARY_METRICS_BY_TYPE['compute/disk'],
  },
  {
    test: (key) => key.includes('compute/vmss') || key.includes('virtualmachinescalesets'),
    metrics: TREND_SUMMARY_METRICS_BY_TYPE['compute/vmss'],
  },
  {
    test: (key) => key.includes('compute/vm') || key.includes('microsoft.compute/virtualmachines'),
    metrics: TREND_SUMMARY_METRICS_BY_TYPE['compute/vm'],
  },
  {
    test: (key) => key.includes('storage/account') || key.includes('microsoft.storage/storageaccounts'),
    metrics: TREND_SUMMARY_METRICS_BY_TYPE['storage/account'],
  },
  {
    test: (key) => key.includes('messaging/servicebus') || key.includes('microsoft.servicebus'),
    metrics: TREND_SUMMARY_METRICS_BY_TYPE['messaging/servicebus'],
  },
  {
    test: (key) => key.includes('messaging/eventhub') || key.includes('microsoft.eventhub'),
    metrics: TREND_SUMMARY_METRICS_BY_TYPE['messaging/eventhub'],
  },
  {
    test: (key) => key.includes('database/cosmos') || key.includes('microsoft.documentdb'),
    metrics: TREND_SUMMARY_METRICS_BY_TYPE['database/cosmosdb'],
  },
  {
    test: (key) => key.includes('database/redis') || key.includes('microsoft.cache/redis'),
    metrics: TREND_SUMMARY_METRICS_BY_TYPE['database/redis'],
  },
  {
    test: (key) => key.includes('database/postgresql') || key.includes('microsoft.dbforpostgresql'),
    metrics: TREND_SUMMARY_METRICS_BY_TYPE['database/postgresql'],
  },
  {
    test: (key) => key.includes('database/sql') || key.includes('microsoft.sql/servers'),
    metrics: TREND_SUMMARY_METRICS_BY_TYPE['database/sql'],
  },
  {
    test: (key) => key.includes('appservice/webapp') || key.includes('microsoft.web/sites'),
    metrics: TREND_SUMMARY_METRICS_BY_TYPE['appservice/webapp'],
  },
  {
    test: (key) => key.includes('appservice/plan') || key.includes('microsoft.web/serverfarms'),
    metrics: TREND_SUMMARY_METRICS_BY_TYPE['appservice/plan'],
  },
  {
    test: (key) => key.includes('containers/aks') || key.includes('microsoft.containerservice/managedclusters'),
    metrics: TREND_SUMMARY_METRICS_BY_TYPE['containers/aks'],
  },
  {
    test: (key) => key.includes('network/appgateway') || key.includes('microsoft.network/applicationgateways'),
    metrics: TREND_SUMMARY_METRICS_BY_TYPE['network/appgateway'],
  },
  {
    test: (key) => key.includes('network/loadbalancer') || key.includes('microsoft.network/loadbalancers'),
    metrics: TREND_SUMMARY_METRICS_BY_TYPE['network/loadbalancer'],
  },
];

export function resolveArmTypeFromResource(resource) {
  if (!resource) return '';
  const props = resource.properties || {};
  const fromProps = props.armResourceType || props.arm_resource_type || resource.armResourceType;
  if (fromProps && String(fromProps).includes('/')) {
    return String(fromProps).toLowerCase();
  }
  const rid = String(resource.id || resource.resource_id || '').toLowerCase();
  const type = String(resource.type || '').toLowerCase();
  if (type.includes('/')) return type;
  if (rid.includes('/providers/')) {
    const parts = rid.split('/');
    const idx = parts.indexOf('providers');
    if (idx >= 0 && parts[idx + 2]) {
      return `${parts[idx + 1]}/${parts[idx + 2]}`.toLowerCase();
    }
  }
  return type;
}

function canonicalTypeFromArmHints(resource) {
  const armType = resolveArmTypeFromResource(resource);
  const rid = String(resource?.id || resource?.resource_id || '').toLowerCase();
  for (const [fragment, canonical] of ARM_FRAGMENT_TO_CANONICAL) {
    if (armType.includes(fragment) || rid.includes(fragment)) {
      return canonical;
    }
  }
  return '';
}

/** Resolve canonical resource type for drawer tabs (api path, row fields, ARM id). */
export function resolveDrawerCanonicalType(resource, apiPath = '') {
  const canonicalFromPath = syncTypesForApiPath(apiPath)[0] || null;
  if (canonicalFromPath) return canonicalFromPath;

  const fromRow = resource?.canonical_type || resource?.canonicalType;
  if (fromRow && String(fromRow).includes('/')) return fromRow;

  const fromArm = canonicalTypeFromArmHints(resource);
  if (fromArm) return fromArm;

  const armType = resolveArmTypeFromResource(resource);
  if (armType && armType.includes('/')) return armType;

  return resource?.type || '';
}

export function resourceUsesCpuMemoryTrends(resource, apiPath = '') {
  const key = String(resolveDrawerCanonicalType(resource, apiPath) || resolveArmTypeFromResource(resource)).toLowerCase();
  return key.includes('compute/vm') || key.includes('virtualmachine');
}

function metricsForKey(key = '', armType = '') {
  const canonical = String(key || '').trim().toLowerCase();
  if (TREND_SUMMARY_METRICS_BY_TYPE[canonical]) {
    return [...TREND_SUMMARY_METRICS_BY_TYPE[canonical]];
  }
  const normalized = String(canonical || armType || '').toLowerCase();
  const profile = TREND_METRIC_PROFILES.find(
    (entry) => entry.test(normalized) || (armType && entry.test(String(armType).toLowerCase())),
  );
  return profile ? [...profile.metrics] : [];
}

/** True when this resource type has configured trend summary metrics. */
export function hasTrendSummaryMetrics(canonicalType = '', armType = '') {
  return metricsForKey(canonicalType, armType).length > 0;
}

export function noTrendSummaryMetricsMessage() {
  return 'No utilization metrics for this resource type';
}

/** Primary monitor fact keys for resource-type trend charts. */
export function trendMetricKeysForResource(resource, apiPath = '') {
  const canonical = String(resolveDrawerCanonicalType(resource, apiPath) || '').toLowerCase();
  const armType = resolveArmTypeFromResource(resource).toLowerCase();
  return metricsForKey(canonical || armType, armType);
}

export function trendMetricKeysForType(canonicalType = '', armType = '') {
  return metricsForKey(canonicalType, armType);
}

export function insufficientTrendMessage(metricLabel) {
  return `Insufficient data for ${metricLabel}. Sync Azure Monitor metrics to build trend history.`;
}

/**
 * Trend summary cards to render in the drawer.
 * Hides cards when a utilization chart already covers the same metric.
 * Property-backed static cards are always kept.
 */
export function visibleTrendSummaryCards(summaryCards = [], metricKeys = [], chartedFactKeys = []) {
  if (!summaryCards.length) return [];

  const charted = chartedFactKeys instanceof Set
    ? chartedFactKeys
    : new Set(chartedFactKeys);

  return summaryCards.filter((card) => {
    const spec = metricKeys.find((entry) => entry.label === card.label);
    if (!spec) return true;
    if (spec.static) return true;
    return !charted.has(spec.factKey);
  });
}
