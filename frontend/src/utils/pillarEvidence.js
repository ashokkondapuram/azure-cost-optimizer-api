/** Group evidence checks and trigger metrics by optimization pillar. */

import { formatCategoryLabel } from './taxonomy';

export const PILLAR_ORDER = [
  'cost',
  'performance',
  'reliability',
  'security',
  'governance',
  'operations',
  'data',
  'other',
];

export const PILLAR_LABELS = {
  cost: 'Cost',
  performance: 'Performance',
  reliability: 'Reliability',
  security: 'Security',
  governance: 'Governance',
  operations: 'Operations',
  data: 'Data',
  other: 'Other signals',
};

const SECURITY_FACT_KEYS = new Set([
  'missing_tags',
  'risky_rules',
  'public_network_access',
  'publicNetworkAccess',
  'enablePurgeProtection',
  'enableSoftDelete',
  'has_private_endpoint',
  'encryption',
]);

const RELIABILITY_FACT_KEYS = new Set([
  'deadletter_messages',
  'replication_count',
  'provisioning_state',
  'provisioningState',
  'uptime_hours',
  'age_days',
  'time_created',
  'last_ownership_update',
  'last_ownership_update_time',
  'kubernetes_version',
]);

const PERFORMANCE_FACT_KEYS = new Set([
  'avg_cpu_pct',
  'avg_memory_pct',
  'avg_mem_pct',
  'memory_usage_pct',
  'disk_queue_depth',
  'disk_used_pct',
  'disk_iops_utilization_pct',
  'disk_throughput_utilization_pct',
  'cluster_cpu_pct',
  'cluster_mem_pct',
  'normalized_ru_pct',
  'normalized_ru_peak_pct',
]);

const COST_FACT_KEYS = new Set([
  'monthly_cost',
  'monthly_cost_usd',
  'current_spend_usd',
  'forecast_spend_usd',
  'amount',
  'azure_service_name',
]);

const SECURITY_SIGNAL_PATTERN = /tag|public|encrypt|security|nsg|vault|auth|private endpoint/i;
const RELIABILITY_SIGNAL_PATTERN = /backup|deprecated|deadletter|provisioning|uptime|ownership|replication|availability|dr\b|disaster/i;
const PERFORMANCE_SIGNAL_PATTERN = /cpu|memory|iops|throughput|latency|queue|utilization|ru\b|throttl|disk read|disk write|egress|network/i;
const COST_SIGNAL_PATTERN = /month-to-date|monthly cost|on-demand spend|compute spend|mtd cost|azure service \(billing\)|cost spike|spend/i;
const GOVERNANCE_SIGNAL_PATTERN = /region|policy|compliance|approved|residency|governance|location/i;

function normalizePillar(value) {
  const key = String(value || '').trim().toLowerCase();
  if (!key) return 'other';
  if (PILLAR_ORDER.includes(key)) return key;
  if (key === 'perf') return 'performance';
  if (key === 'sec') return 'security';
  return 'other';
}

export function pillarLabel(pillar) {
  const key = normalizePillar(pillar);
  if (PILLAR_LABELS[key]) return PILLAR_LABELS[key];
  return formatCategoryLabel(key);
}

export function inferCheckPillar(check) {
  if (check?.pillar) return normalizePillar(check.pillar);
  const factKey = String(check?.fact_key || check?.value_key || check?.valueKey || '').trim();
  const signal = String(check?.signal || '');

  if (SECURITY_FACT_KEYS.has(factKey) || SECURITY_SIGNAL_PATTERN.test(signal)) return 'security';
  if (RELIABILITY_FACT_KEYS.has(factKey) || RELIABILITY_SIGNAL_PATTERN.test(signal)) return 'reliability';
  if (PERFORMANCE_FACT_KEYS.has(factKey) || PERFORMANCE_SIGNAL_PATTERN.test(signal)) return 'performance';
  if (COST_FACT_KEYS.has(factKey) || COST_SIGNAL_PATTERN.test(signal)) return 'cost';
  if (GOVERNANCE_SIGNAL_PATTERN.test(signal)) return 'governance';
  return 'other';
}

export function groupChecksByPillar(checks = []) {
  const buckets = {};
  for (const check of checks) {
    const pillar = inferCheckPillar(check);
    if (!buckets[pillar]) buckets[pillar] = [];
    buckets[pillar].push(check);
  }
  return PILLAR_ORDER
    .filter((pillar) => buckets[pillar]?.length)
    .map((pillar) => ({
      pillar,
      label: pillarLabel(pillar),
      checks: buckets[pillar],
    }));
}

/** Split trigger metrics into pillar-specific rows (cost vs performance effects). */
export function groupTriggerMetricsByPillar(triggerMetrics = []) {
  const buckets = { cost: [], performance: [] };

  for (const item of triggerMetrics) {
    if (item?.effect_cost) {
      buckets.cost.push({
        ...item,
        pillarEffect: item.effect_cost,
        pillarKey: 'cost',
      });
    }
    if (item?.effect_performance) {
      buckets.performance.push({
        ...item,
        pillarEffect: item.effect_performance,
        pillarKey: 'performance',
      });
    }
    if (!item?.effect_cost && !item?.effect_performance) {
      buckets.performance.push({
        ...item,
        pillarEffect: item.threshold || '',
        pillarKey: 'performance',
      });
    }
  }

  return ['cost', 'performance']
    .filter((pillar) => buckets[pillar]?.length)
    .map((pillar) => ({
      pillar,
      label: pillarLabel(pillar),
      items: buckets[pillar],
    }));
}

export function extractRegionMigration(evidence, whatIf = null) {
  const ev = evidence && typeof evidence === 'object' ? evidence : {};
  const scenario = whatIf && typeof whatIf === 'object' ? whatIf : ev.what_if;

  const recommendedRegion = scenario?.recommendedTargetRegion
    || ev.recommendedRegion
    || scenario?.proposedState?.region
    || null;
  const recommendedRegionDisplay = scenario?.recommendedTargetRegionDisplay
    || ev.recommendedRegionDisplay
    || recommendedRegion;

  const currentRegion = scenario?.currentState?.region
    || ev.currentRegion
    || ev.location
    || null;

  if (!recommendedRegion && !recommendedRegionDisplay) return null;

  return {
    currentRegion,
    recommendedRegion,
    recommendedRegionDisplay: recommendedRegionDisplay || recommendedRegion,
    action: scenario?.action || null,
  };
}

export function findingRecommendedRegion(finding) {
  if (!finding) return null;
  const migration = extractRegionMigration(finding.evidence, finding.evidence?.what_if);
  return migration?.recommendedRegionDisplay || migration?.recommendedRegion || null;
}

export function groupFindingsByPillar(findings = []) {
  const buckets = {};
  for (const finding of findings) {
    const pillar = normalizePillar(finding?.pillar || finding?.category || 'other');
    if (!buckets[pillar]) buckets[pillar] = [];
    buckets[pillar].push(finding);
  }
  return PILLAR_ORDER
    .filter((pillar) => buckets[pillar]?.length)
    .map((pillar) => ({
      pillar,
      label: pillarLabel(pillar),
      findings: buckets[pillar],
    }));
}
