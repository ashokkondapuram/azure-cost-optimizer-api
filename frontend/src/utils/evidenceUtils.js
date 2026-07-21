/** Normalize API/persisted evidence payloads for safe UI rendering. */

import { enrichServiceEvidenceFilter } from '../it-services/registry';

function coerceText(value) {
  if (value == null || value === '') return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (typeof value === 'object') {
    const named = value.name ?? value.code ?? value.label ?? value.value;
    if (named != null && named !== '') return coerceText(named);
    try {
      return JSON.stringify(value);
    } catch {
      return '';
    }
  }
  return String(value);
}

const RESOURCE_DETAIL_LABELS = {
  vm_size: 'VM size',
  avg_cpu_pct: 'Average CPU utilization',
  disk_state: 'Disk state',
  size_gb: 'Disk size (GB)',
  age_days: 'Age (days)',
  time_created: 'Created',
  last_ownership_update: 'Last ownership update time',
  last_ownership_update_time: 'Last ownership update time',
  last_owner_name: 'Last owner name',
  last_managed_by: 'Last attached to',
  sku: 'SKU',
  arm_resource_type: 'ARM resource type',
  resource_type: 'Resource type',
  location: 'Location',
  state: 'State',
  provisioning_state: 'Provisioning state',
  provisioningState: 'Provisioning state',
  http_listener_count: 'HTTP listeners',
  backend_pool_count: 'Backend pools',
  health_probe_count: 'Health probes',
  subnet_count: 'Associated subnets',
  kubernetes_version: 'Kubernetes version',
  pool_count: 'Node pools',
  node_count: 'Node count',
  idle_nodes: 'Idle nodes',
  access_tier: 'Access tier',
  egress_bytes: 'Data egress',
  sku_display: 'Replication',
  tier: 'Tier',
  capacity: 'Capacity',
  environment: 'Environment',
  alwaysOn: 'Always On',
  has_vm: 'Attached to VM',
  has_private_endpoint: 'Private endpoint',
  app_count: 'Hosted apps',
  system_pool_count: 'System node pools',
  enableSoftDelete: 'Soft delete enabled',
  enablePurgeProtection: 'Purge protection',
  allocation: 'Allocation method',
  cost_export_only: 'Cost export only (not in inventory sync)',
  resource_group: 'Resource group',
  missing_tags: 'Missing required tags',
  storage_gb: 'Storage (GB)',
  used_pct: 'Budget utilization',
  amount: 'Budget limit',
  current_spend_usd: 'Current spend',
  forecast_spend_usd: 'Forecast spend',
  risky_rules: 'Risky NSG rules',
  replication_count: 'Replication count',
  capabilities: 'Capabilities',
  nic_count: 'Network interfaces',
  source_disk_id: 'Source disk',
  source_resource_id: 'Source resource',
};

const RESOURCE_DETAIL_SKIP = new Set([
  'summary', 'checks', 'determination', 'data_source', 'source',
  'savings_methodology', 'monthly_cost', 'monthly_cost_usd',
  'min_monthly_cost', 'savings_factor', 'cost_export_only',
  'passed', 'status', 'resource_details', 'sku_label',
  'optimization_metrics',
  'ai_insight',
  'rule_engine',
  'service_name', 'properties', 'tags',
  'azure_service_name', 'billing_service_name', 'billingServiceName',
  'estimated_savings_usd', 'annualized_savings_usd',
  'confidence_score', 'waste_score',
  // Assessment contracts + engine metadata
  'required_evidence', 'evidence_rows', 'evidence_factors',
  'exclude_inventory_facts', '_evidence_meta', 'assessment_file', 'rule_thresholds',
  'engine', 'rule_source', 'sub_engine', 'recommendation_action', 'pillar', 'confidence',
  'offer_type', 'region_count', 'resource_elements', 'signals',
  'data_quality', 'creation_data', 'creationData',
  'max_unattached_disk_days', 'disk_io_idle_bps', 'disk_idle_min_size_gb',
  'disk_iops_block_downgrade_pct', 'disk_iops_high_util_pct', 'disk_throughput_high_util_pct',
  'evaluation_window_days', 'min_monthly_savings_usd', 'disk_capacity_used_pct_max',
  'disk_queue_depth_contention',
  'disk_read_bps', 'disk_write_bps', 'disk_read_iops', 'disk_write_iops',
  'disk_iops_utilization_pct', 'disk_throughput_utilization_pct', 'disk_combined_iops',
  'provisioned_iops', 'provisioned_mbps',
  // Shown in drawer meta or optimization_metrics.performance
  'location', 'resource_group', 'state', 'sku', 'vm_size',
  'avg_cpu_pct', 'avg_memory_pct', 'avg_mem_pct', 'memory_usage_pct',
  'used_pct', 'idle_nodes', 'idle_node_ratio', 'node_count', 'pool_count',
  'uptime_hours', 'age_days', 'last_owner_name', 'time_created',
  'last_ownership_update', 'last_ownership_update_time', 'size_gb', 'storage_gb',
  'http_listener_count', 'backend_pool_count', 'subnet_count', 'app_count',
  'nic_count', 'replication_count', 'power_state', 'provisioning_state',
  'provisioningState', 'disk_state', 'allocation', 'tier', 'access_tier',
  'kubernetes_version', 'alwaysOn', 'has_vm', 'has_private_endpoint',
  'has_lifecycle_policy', 'autoscaler_enabled', 'all_backends_empty',
  'pricing_model', 'environment', 'arm_resource_type', 'resource_type',
  'used_capacity_bytes', 'transaction_count',
]);

const COST_CHECK_VALUE_KEYS = new Set([
  'monthly_cost', 'monthly_cost_usd', 'min_monthly_cost',
  'current_spend_usd', 'forecast_spend_usd', 'amount', 'azure_service_name',
]);

const COST_CHECK_SIGNAL_PATTERN = /month-to-date|monthly cost|on-demand spend|compute spend|mtd cost|azure service \(billing\)/i;

const PERFORMANCE_CHECK_VALUE_KEYS = new Set([
  'avg_cpu_pct', 'avg_memory_pct', 'avg_mem_pct', 'memory_usage_pct', 'used_pct',
  'idle_nodes', 'idle_node_ratio', 'node_count', 'pool_count', 'uptime_hours',
  'age_days', 'last_owner_name', 'time_created', 'last_ownership_update',
  'size_gb', 'storage_gb', 'http_listener_count', 'backend_pool_count',
  'subnet_count', 'app_count', 'nic_count', 'replication_count', 'power_state',
  'provisioning_state', 'disk_state', 'state', 'allocation', 'vm_size', 'sku',
  'tier', 'access_tier', 'kubernetes_version', 'alwaysOn', 'has_vm',
  'has_private_endpoint', 'has_lifecycle_policy', 'autoscaler_enabled',
  'all_backends_empty', 'pricing_model', 'environment', 'resource_group',
  'arm_resource_type', 'resource_type', 'used_capacity_bytes', 'transaction_count',
]);

const PERFORMANCE_CHECK_SIGNAL_PATTERN = /peak cpu|average cpu|cpu utilization|memory utilization|peak memory/i;

const ENGINE_SCORE_METRIC_IDS = new Set(['waste_score', 'confidence_score']);

const PRIMARY_COST_METRIC_IDS = new Set(['mtd_cost', 'estimated_savings', 'azure_service']);

/** Inventory/configuration facts — shown in Properties, not evidence panels. */
export const PROPERTY_NOT_EVIDENCE_KEYS = new Set([
  'node_count', 'pool_count', 'kubernetes_version', 'kubernetes_minor',
  'supported_versions', 'default_version', 'version_source',
  'sku', 'sku_name', 'sku_tier', 'tier', 'state', 'resource_state',
  'provisioning_state', 'provisioningState', 'vm_size', 'scale_set_priority',
  'pool_name', 'environment', 'system_pool_count', 'app_count',
  'location', 'resource_group', 'arm_resource_type', 'resource_type',
  'alwaysOn', 'has_vm', 'has_private_endpoint', 'pricing_model', 'allocation',
  'access_tier', 'nic_count', 'replication_count', 'http_listener_count',
  'backend_pool_count', 'subnet_count', 'capacity', 'size_gb', 'storage_gb',
  'age_days', 'time_created', 'last_owner_name', 'last_ownership_update',
  'last_ownership_update_time', 'suggested_sku', 'suggested_family', 'sizing_action',
  'missing_tags', 'api_type', 'consistency_level', 'ha_mode', 'version',
  'backup_retention_days', 'multi_write_enabled', 'automatic_failover_enabled',
  'free_tier_enabled', 'persistence_enabled', 'shard_count', 'record_set_count',
  'endpoint_count', 'ddos_protection', 'plan_sku', 'database_count', 'license_type',
  'enableSoftDelete', 'enablePurgeProtection', 'public_ip_count', 'throughput_gbps',
  'disk_state', 'all_backends_empty', 'has_lifecycle_policy', 'disk_sku',
  'replication_regions', 'automatic_failover', 'multi_write', 'serverless_enabled',
  'license_type', 'pricing_tier', 'sku_family', 'current_sku', 'target_sku',
  'engine', 'rule_source', 'sub_engine', 'recommendation_action', 'pillar', 'confidence',
  'offer_type', 'region_count', 'resource_elements', 'signals',
]);

export const PROPERTY_NOT_EVIDENCE_LABELS = new Set([
  'Node count', 'Node pools', 'Resource state', 'SKU', 'Kubernetes version',
  'Service tier', 'Power state', 'Provisioning state', 'VM SKU', 'Environment tag',
  'Pool name', 'System node pools', 'Hosted apps', 'Location', 'Resource group',
  'ARM resource type', 'Access tier', 'Allocation method', 'Replication count',
  'Associated subnets', 'HTTP listeners', 'Backend pools', 'Network interfaces',
  'Disk size (GB)', 'Storage (GB)', 'Age (days)', 'Created', 'Tier',
  'Suggested SKU', 'Suggested family', 'Sizing action', 'Missing tags',
  'API type', 'Consistency level', 'HA mode', 'Version', 'Disk state',
  'Disk SKU', 'Pricing model', 'Always On', 'Attached to VM',
]);

export function isInventoryPropertyEvidence(label, factKey = '') {
  const key = String(factKey || '').trim();
  if (key && PROPERTY_NOT_EVIDENCE_KEYS.has(key)) return true;
  const text = String(label || '').trim();
  return PROPERTY_NOT_EVIDENCE_LABELS.has(text);
}

function humanizeKey(key) {
  if (RESOURCE_DETAIL_LABELS[key]) return RESOURCE_DETAIL_LABELS[key];
  return key
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatDetailValue(value) {
  if (value == null || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'number') {
    if (Number.isInteger(value)) return value.toLocaleString();
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  if (Array.isArray(value)) {
    if (!value.length) return '—';
    if (value.every((v) => typeof v !== 'object')) return value.join(', ');
    return `${value.length} items`;
  }
  if (typeof value === 'object') return coerceText(value);
  return String(value);
}

export function normalizeEvidence(raw) {
  if (raw == null || raw === '') return null;
  let value = raw;
  if (typeof value === 'string') {
    try {
      value = JSON.parse(value);
    } catch {
      return null;
    }
  }
  if (typeof value !== 'object' || Array.isArray(value)) return null;
  return value;
}

export function evidenceChecks(evidence) {
  const checks = evidence?.checks;
  return Array.isArray(checks) ? checks : [];
}

/** Technical/utilization signals only — metrics appear in optimization_metrics tables. */
export function evidenceTechnicalChecks(evidence) {
  return evidenceChecks(evidence).filter((check) => {
    const signal = check?.signal || '';
    const valueKey = check?.value_key || check?.valueKey || '';
    if (COST_CHECK_VALUE_KEYS.has(valueKey)) return false;
    if (COST_CHECK_SIGNAL_PATTERN.test(signal)) return false;
    if (PERFORMANCE_CHECK_VALUE_KEYS.has(valueKey)) return false;
    if (PERFORMANCE_CHECK_SIGNAL_PATTERN.test(signal)) return false;
    return true;
  });
}

export function evidenceSavingsMethodology(evidence) {
  const raw = evidence?.savings_methodology;
  if (!raw) return null;
  if (typeof raw === 'string') {
    return { description: raw };
  }
  if (typeof raw === 'object' && !Array.isArray(raw)) {
    return {
      description: coerceText(raw.description) || null,
      formula: coerceText(raw.formula) || null,
      method: raw.method,
    };
  }
  return null;
}

export function formatEvidenceLabel(value) {
  const text = coerceText(value);
  const DETERMINATION_LABELS = {
    idle_no_listeners: 'Idle — no HTTP listeners',
    low_throughput: 'Low throughput',
    idle_no_backends: 'Idle — no backend targets',
    low_traffic: 'Low traffic',
    cross_family_candidate: 'Cross-family SKU candidate',
    vm_sku_rightsizing: 'VM SKU rightsizing',
    underutilized_cpu: 'Underutilized CPU',
    oversized_sku: 'Oversized SKU',
  };
  return DETERMINATION_LABELS[text] || text.replace(/_/g, ' ');
}

export function evidenceDataSourceLabel(dataSource) {
  const label = formatEvidenceLabel(dataSource);
  if (!label) return '';
  if (label.includes('cost export')) return 'Cost export metadata + resource attributes';
  if (label.includes('synced inventory')) return 'Synced Azure inventory';
  if (label.includes('azure monitor')) return 'Azure Monitor metrics';
  if (label.includes('live')) return 'Live Azure API';
  return label;
}

const METRIC_STATUS_LABELS = {
  underutilized: 'Underutilized',
  low: 'Low utilization',
  healthy: 'Healthy',
  high: 'High utilization',
  critical: 'Critical',
  stale: 'Stale',
  unavailable: 'Not available',
  medium: 'Medium opportunity',
  informational: 'Informational',
  above_threshold: 'Above threshold',
};

export function evidenceOptimizationMetrics(evidence, options = {}) {
  const ev = normalizeEvidence(evidence);
  const block = ev?.optimization_metrics;
  if (!block || typeof block !== 'object') return null;
  const hideEngineScores = options.hideEngineScores !== false;
  const cost = (Array.isArray(block.cost) ? block.cost : [])
    .filter((m) => PRIMARY_COST_METRIC_IDS.has(m.id));
  let performance = Array.isArray(block.performance) ? block.performance : [];
  if (hideEngineScores) {
    performance = performance.filter((m) => !ENGINE_SCORE_METRIC_IDS.has(m.id));
  }
  performance = performance.filter((m) => m.status !== 'unavailable');
  performance = performance.filter(
    (m) => !isInventoryPropertyEvidence(m.label, m.fact_key || m.id),
  );
  if (!cost.length && !performance.length) return null;
  return {
    cost,
    performance,
    dataQuality: block.data_quality || '',
    component: block.component || '',
    displayMode: block.display_mode || '',
  };
}

/** Compact cost block: MTD cost + estimated savings (+ billing service when relevant). */
export function evidenceCostSummary(evidence, options = {}) {
  const metrics = evidenceOptimizationMetrics(evidence, options);
  if (!metrics?.cost?.length) return null;
  if (options.hideEstimatedSavings) {
    return metrics.cost.filter((m) => m.id !== 'estimated_savings');
  }
  return metrics.cost;
}

/** Azure retail list-price block when SKU/tier pricing is present in evidence. */
export function extractRetailPricing(evidence) {
  const ev = normalizeEvidence(evidence);
  if (!ev) return null;
  const current = ev.current_sku_monthly_usd ?? ev.current_tier_monthly_usd;
  const suggested = ev.suggested_sku_monthly_usd ?? ev.suggested_tier_monthly_usd;
  if (current == null && suggested == null) return null;
  return {
    currentMonthlyUsd: current,
    suggestedMonthlyUsd: suggested,
    savingsUsd: ev.estimated_monthly_savings_usd ?? ev.retail_monthly_savings_usd,
    pricingStatus: ev.pricing_status,
    pricingSource: ev.pricing_source,
  };
}

export function formatUsdAmount(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function optimizationMetricStatusLabel(status) {
  if (!status) return '';
  return METRIC_STATUS_LABELS[status] || formatEvidenceLabel(status);
}

export function optimizationDataQualityLabel(dataQuality) {
  const labels = {
    azure_monitor: 'Azure Monitor metrics',
    k8s_agent: 'Kubernetes agent metrics',
    mixed: 'Azure Monitor + Kubernetes agent',
    cost_export_with_inventory: 'Cost export + inventory attributes',
    cost_export_only: 'Cost export only',
    inventory_and_cost: 'Synced inventory + cost data',
    azure_monitor_and_cost: 'Azure Monitor + cost data',
    cost_only: 'Cost data only',
    inventory_proxy: 'Inventory attributes (proxy metrics)',
    limited: 'Limited metric coverage',
  };
  return labels[dataQuality] || formatEvidenceLabel(dataQuality);
}

const UTILIZATION_TREND_LABELS = {
  growing: 'Rising',
  increasing: 'Rising',
  shrinking: 'Falling',
  decreasing: 'Falling',
  stable: 'Stable',
  unknown: 'Insufficient data',
};

/** Render API utilization trend strings or utilization_trend() objects for UI. */
export function formatUtilizationTrend(trend) {
  if (trend == null || trend === '') return null;
  if (typeof trend === 'string') {
    const key = trend.toLowerCase();
    return UTILIZATION_TREND_LABELS[key] || formatEvidenceLabel(trend);
  }
  if (typeof trend !== 'object') return coerceText(trend);

  if (trend.insufficient_history) {
    const weeks = Number(trend.sample_count);
    if (Number.isFinite(weeks) && weeks > 0) {
      return `Insufficient data (${weeks} wk)`;
    }
    return 'Insufficient data';
  }

  const slope = String(trend.slope || 'unknown').toLowerCase();
  const parts = [UTILIZATION_TREND_LABELS[slope] || 'Stable'];

  const growth = trend.growth_rate_per_week;
  if (growth != null && Number.isFinite(Number(growth))) {
    const signed = Number(growth) > 0 ? `+${Number(growth)}` : String(Number(growth));
    parts.push(`${signed}%/wk`);
  }

  const current = trend.current_value;
  const projected = trend.projected_4w;
  if (current != null && projected != null) {
    parts.push(`${Number(current).toFixed(1)}% → ${Number(projected).toFixed(1)}% (4w)`);
  }

  return parts.join(' · ');
}

export function isPercentOptimizationMetric(metric) {
  const unit = String(metric?.unit || '').trim().toLowerCase();
  if (unit === '%' || unit === 'ratio') return true;
  return String(metric?.formatted ?? '').includes('%');
}

export function parseOptimizationPercentValue(formatted, raw) {
  const from = formatted ?? raw;
  if (from == null) return null;
  if (!String(from).includes('%') && typeof raw !== 'number' && !String(raw ?? '').includes('%')) {
    return null;
  }
  const n = parseFloat(String(from).replace(/[^\d.]/g, ''));
  return Number.isNaN(n) ? null : n;
}

const OPTIMIZATION_METRIC_IDS = new Set([
  'suggested_sku',
  'sizing_action',
  'suggested_family',
  'suggested_tier',
  'estimated_savings',
]);

const DRAWER_DETAIL_SKIP_KEYS = new Set([
  'vm_size',
  'sku',
  'sku_tier',
  'location',
  'resource_group',
  'arm_resource_type',
  'resource_state',
  'state',
  'canonical_resource_type',
  'resource_type',
]);

/** Hide metrics already shown in the resource drawer header/meta. */
export function filterPerformanceMetricsForContext(metrics = [], inventoryContext = null) {
  if (!Array.isArray(metrics) || !metrics.length) return metrics;

  let filtered = metrics;

  if (inventoryContext) {
    const hideIds = new Set();
    if (inventoryContext.sku) hideIds.add('sku');
    if (inventoryContext.resourceGroup) hideIds.add('resource_group');
    if (inventoryContext.location) hideIds.add('location');
    if (inventoryContext.armType) hideIds.add('arm_resource_type');
    if (inventoryContext.state) {
      hideIds.add('resource_state');
    }

    enrichServiceEvidenceFilter(hideIds, inventoryContext);

    if (hideIds.size) {
      filtered = filtered.filter((m) => !hideIds.has(m.id));
    }

    filtered = filtered.filter((m) => !OPTIMIZATION_METRIC_IDS.has(m.id));

    const hasDiskState = filtered.some((m) => m.id === 'disk_state');
    if (hasDiskState) {
      filtered = filtered.filter((m) => m.id !== 'resource_state');
    }
  }

  if (inventoryContext?.liveMetricsShown) {
    const liveIds = new Set([
      'avg_cpu', 'avg_memory', 'memory_usage', 'cluster_cpu', 'cluster_memory',
      'used_capacity', 'transactions', 'byte_count', 'throughput', 'requests',
      'storage_utilization', 'disk_read', 'disk_write', 'api_hits', 'pull_count',
      'total_ru', 'ops_per_sec', 'snat_connections', 'healthy_hosts',
    ]);
    filtered = filtered.filter((m) => !liveIds.has(m.id));
  }

  return filtered;
}

function normalizeText(value) {
  return String(value || '').trim().toLowerCase();
}

/** Drop checks whose signal already appears in the metrics table. */
export function dedupeChecksAgainstMetrics(checks = [], metrics = []) {
  if (!checks.length || !metrics.length) return checks;
  const metricLabels = new Set(
    metrics.flatMap((m) => [normalizeText(m.label), normalizeText(m.id)]),
  );
  return checks.filter((check) => {
    const signal = normalizeText(check?.signal);
    if (!signal) return true;
    return ![...metricLabels].some((label) => label && (signal.includes(label) || label.includes(signal)));
  });
}

export function filterDrawerResourceDetails(details = [], inventoryContext = null) {
  if (!inventoryContext || !details?.length) return details;
  return details.filter((row) => !DRAWER_DETAIL_SKIP_KEYS.has(row.key));
}

export function extractResourceTechnicalDetails(evidence) {
  const ev = normalizeEvidence(evidence);
  if (!ev) return [];

  const source = ev.resource_details && typeof ev.resource_details === 'object'
    ? ev.resource_details
    : null;

  const entries = source
    ? Object.entries(source).filter(([key]) => !RESOURCE_DETAIL_SKIP.has(key))
    : Object.entries(ev).filter(([key]) => !RESOURCE_DETAIL_SKIP.has(key));

  return entries
    .filter(([, val]) => val != null && val !== '')
    .map(([key, val]) => ({
      key,
      label: humanizeKey(key),
      value: formatDetailValue(val),
    }))
    .filter((row) => !isInventoryPropertyEvidence(row.label, row.key))
    .sort((a, b) => a.label.localeCompare(b.label));
}

export function isDuplicateEvidenceText(a, b) {
  const left = normalizeText(a);
  const right = normalizeText(b);
  if (!left || !right) return false;
  return left === right || left.includes(right) || right.includes(left);
}

/** Normalize evidence/insight row payloads for safe React rendering. */
export function formatEvidenceRow(row) {
  if (row == null || row === '') return null;
  if (typeof row === 'string') {
    return { label: '', value: row, detail: '', tone: '' };
  }
  if (typeof row !== 'object' || Array.isArray(row)) {
    return { label: '', value: coerceText(row), detail: '', tone: '' };
  }
  const label = coerceText(row.label);
  const value = coerceText(row.value ?? row.formatted ?? row.display_value);
  const detail = coerceText(row.detail || row.hint);
  const tone = String(row.tone || '').trim();
  if (!label && !value) return null;
  return {
    label,
    value,
    detail,
    tone,
    major: Boolean(row.major),
  };
}

const PILLAR_ORDER = ['performance', 'cost', 'reliability', 'security'];

/** Group required_evidence contract rows by pillar for insight canvas / drawer. */
export function evidenceRequiredByPillar(evidence) {
  const ev = normalizeEvidence(evidence);
  const required = Array.isArray(ev?.required_evidence) ? ev.required_evidence : [];
  if (!required.length) return [];

  const metrics = evidenceOptimizationMetrics(ev) || {};
  const perfBySignal = new Map(
    (metrics.performance || []).map((m) => [m.fact_key || m.id, m]),
  );

  const buckets = {};
  required.forEach((item) => {
    const pillar = String(item.pillar || 'performance').toLowerCase();
    if (!buckets[pillar]) buckets[pillar] = [];
    const signal = item.signal || '';
    const metric = perfBySignal.get(signal) || perfBySignal.get(item.signal);
    buckets[pillar].push({
      label: item.label || humanizeKey(signal),
      signal,
      aggregation: item.aggregation || '',
      period: item.period || '',
      unit: item.unit || '',
      thresholdKey: item.threshold_key || '',
      value: metric?.display_value || metric?.value || '—',
      hint: item.threshold_key ? `Threshold: ${item.threshold_key}` : '',
      pillar,
    });
  });

  return PILLAR_ORDER
    .filter((pillar) => buckets[pillar]?.length)
    .map((pillar) => ({
      pillar,
      label: pillar.charAt(0).toUpperCase() + pillar.slice(1),
      items: buckets[pillar],
    }));
}
