/** Insight canvas — map live API data to concept-v2 resource detail shape. */

import { formatDateTime, formatCurrency } from './format';
import { humanizeAzureRegion } from './format';
import { buildRecommendationsPanelModel } from './recommendationEvidence';
import { topFindingHeadline } from './findingFilters';
import { sortFindingsByPriority } from './taxonomy';
import { formatCategoryLabel } from './taxonomy';
import { serviceDisplayNameForRow, iconForRow } from '../config/assetIcons';
import { resourceBilledMtd, resourceRetailMonthly, resourceCostBlock, resourceRetailCurrency } from './costCurrency';
import { mapSourceChip, mapSeverityChip, resolveWorkflowStatus } from './actionCentreV2Utils';
import { INVENTORY_API_PATH } from './resourceRowId';
import { formatPowerState, toDisplayText } from './formatDisplay';
import { buildResourcePropertyGroups, filterDisplayablePropertyRows } from './resourcePropertyTabs';
import {
  normalizeEvidence,
  evidenceChecks,
  evidenceOptimizationMetrics,
  extractResourceTechnicalDetails,
  optimizationMetricStatusLabel,
  isPercentOptimizationMetric,
  parseOptimizationPercentValue,
  dedupeChecksAgainstMetrics,
  isDuplicateEvidenceText,
  isInventoryPropertyEvidence,
} from './evidenceUtils';
import { inferCheckPillar } from './pillarEvidence';
import { formatEvidenceCheckValue, formatEvidenceThreshold } from './serviceDisplayUtils';
import { isAnalysisEssentialRow } from './analysisEssentialProperties';
import { resolveDrawerCanonicalType } from './drawerTrendMetrics';
import { labelForFactKey, normalizeMetricRow, formatFactValue } from './resourceMetricsUtils';
import { enrichDrawerResource } from '../it-services/containers-aks/drawer';
import { normalizeAksCluster } from '../it-services/containers-aks/utils/aksNormalize';
import { aggregatePoolUtilization, attachPoolInstances, normalizePoolInstance } from '../it-services/containers-aks/utils/aksPoolUtilization';
import {
  buildDiskInsightFromApi,
  buildPropertyGroups as buildDiskPropertyGroups,
  buildRuleEvidence,
  isDiskCanonicalType,
} from '../disks';
import { apiPathForCanonical } from '../config/resourceApiPaths';

export const CANVAS_SECTION_DEFS = {
  summary: { label: 'Summary', nav: 'Summary' },
  recommendation: { label: 'Recommendation', nav: 'Recommendation' },
  metrics: { label: 'Metrics', nav: 'Metrics' },
  trends: { label: 'Trends', nav: 'Trends' },
  cost: { label: 'Cost', nav: 'Cost' },
  insights: { label: 'Insights', nav: 'Insights' },
  pools: { label: 'Node pools', nav: 'Node pools' },
  instances: { label: 'Instances', nav: 'Instances' },
  properties: { label: 'Properties', nav: 'Properties' },
  advisor: { label: 'Advisor', nav: 'Advisor' },
  tags: { label: 'Tags', nav: 'Tags' },
  history: { label: 'History', nav: 'History' },
};

export const INSIGHT_PROFILES = {
  database: {
    tabs: ['overview', 'properties', 'metrics', 'cost', 'recommendations', 'insights', 'advisor', 'tags', 'actions', 'history'],
    showState: true,
  },
  vm: {
    tabs: ['overview', 'properties', 'metrics', 'instances', 'trends', 'cost', 'recommendations', 'insights', 'tags', 'actions', 'history'],
    showState: true,
  },
  vmss: {
    tabs: ['overview', 'properties', 'metrics', 'instances', 'trends', 'cost', 'recommendations', 'tags', 'actions', 'history'],
    showState: true,
  },
  disk: {
    tabs: ['overview', 'metrics', 'cost', 'recommendations', 'properties', 'tags', 'actions', 'history'],
    sectionOrder: ['summary', 'metrics', 'cost', 'recommendation', 'properties', 'tags', 'history'],
    showState: true,
  },
  storage: {
    tabs: ['overview', 'properties', 'metrics', 'cost', 'recommendations', 'tags', 'actions', 'history'],
    showState: false,
  },
  kubernetes: {
    tabs: ['overview', 'properties', 'pools', 'metrics', 'cost', 'recommendations', 'insights', 'tags', 'actions', 'history'],
    showState: true,
  },
  network: {
    tabs: ['overview', 'properties', 'cost', 'recommendations', 'tags', 'actions', 'history'],
    showState: true,
  },
};

const MAJOR_PROPERTY_LABELS = new Set([
  'sku', 'size', 'disk size', 'disk state', 'state', 'status', 'power state',
  'provisioning state', 'service tier', 'compute size', 'access tier', 'tier',
  'vm size', 'managed by', 'attached to', 'associated resource', 'associated',
  'allocation', 'kind', 'replication', 'encryption', 'kubernetes version',
  'node count', 'backend members', 'ip address', 'autoscale', 'consistency',
  'provisioned throughput', 'zone redundancy', 'server', 'cluster',
]);

/** Performance / pricing labels owned by the SKU panel — not lifecycle or connectivity. */
export const SKU_PANEL_SPEC_LABELS = new Set([
  'provisioned iops', 'provisioned mb/s', 'iops', 'throughput',
  'dtu', 'vcpus', 'vcores', 'memory', 'peak utilization', 'storage used',
  'ru/s', 'provisioned throughput', 'max size', 'used capacity',
  'vcores per node', 'memory per node', 'min ru/s', 'max ru/s',
]);

const SKU_PANEL_PRICING_LABELS = new Set([
  'monthly cost', 'mtd billed', 'retail price', 'est. monthly cost', 'est. savings',
]);

const CANVAS_PROPERTY_CATEGORY_ORDER = ['Configuration', 'Connectivity', 'Lifecycle', 'Security'];

const LIFECYCLE_PROPERTY_RE = /provision|created|synced|restore|updated|idle|timecreated|last.?sync|agent status|earliest restore|ownership update/i;
const CONNECTIVITY_PROPERTY_RE = /network|connect|attach|managedby|managed by|server|private ip|public ip|vnet|subnet|elastic pool|backend|fqdn|dns|ip address|accelerated|virtual network|associated resource|associated|nic|load balancer/i;
const SECURITY_PROPERTY_RE = /encrypt|tls|security|access policy|public network|firewall|key source|https only|minimum tls/i;

/** Labels/keys excluded from canvas Properties — header duplicates and internal IDs. */
const ASSESSMENT_PROPERTY_DENYLIST_RE = /resource\s*id|arm\s*id|subscription\s*id|tenant\s*id|correlation\s*id|\/subscriptions\//i;

const HEADER_DUPLICATE_PROPERTY_LABELS = new Set([
  'name', 'resource name', 'resource group', 'type', 'region', 'location', 'sku',
]);

const ARM_PATH_VALUE_RE = /^\/subscriptions\/[0-9a-f-]+\/resourcegroups\//i;

/** AKS Properties section — portal-style cluster fields only (label matching, case-insensitive). */
export const AKS_PROPERTIES_ALLOWLIST = new Set([
  'kubernetes version',
  'node provisioning profile',
  'mode',
  'default node pools',
  'outbound type',
  'load balancer sku',
  'load balancer profile',
  'effective outbound ips',
  'power state',
]);

const AKS_PROPERTY_KEY_PATTERNS = [
  'kubernetesversion',
  'nodeprovisioningprofile',
  'defaultnodepools',
  'outboundtype',
  'loadbalancersku',
  'loadbalancerprofile',
  'effectiveoutbound',
  'managedoutbound',
  'powerstate',
];

export function isAksResourceType(resourceType = '') {
  const canonicalType = String(resourceType || '').toLowerCase();
  return canonicalType === 'containers/aks' || canonicalType === 'kubernetes';
}

/** True when an AKS property row belongs in Properties (insight canvas + drawer). */
export function isAksAllowedProperty(label = '', key = '') {
  const labelText = String(label || '').trim();
  const labelLower = labelText.toLowerCase();
  const labelNorm = normalizePropertyToken(labelLower);
  const keyNorm = normalizePropertyToken(key);
  const keyLower = String(key || '').trim().toLowerCase();

  if (!labelText && !keyNorm) return false;

  // Node pool fields belong in the Node pools section, not Properties.
  if (keyNorm.includes('agentpoolprofile') && !keyNorm.includes('defaultnodepool')) {
    return false;
  }

  // Mode — cluster node provisioning (Manual / Auto), not per-pool System/User mode.
  if (labelNorm === 'mode' || keyNorm.endsWith('mode') || keyLower.endsWith('.mode')) {
    if (keyNorm.includes('agentpoolprofile')) return false;
    if (keyNorm.includes('nodeprovisioningprofile') || labelNorm === 'mode') return true;
    return false;
  }

  // Power state — cluster scalar only; pool/instance states belong in Node pools.
  if (labelNorm.includes('powerstate') || keyNorm === 'powerstate' || labelLower.includes('power state')) {
    if (keyNorm.includes('agentpoolprofile')) return false;
    if (String(key || '').includes('.')) return false;
    return true;
  }

  for (const allowed of AKS_PROPERTIES_ALLOWLIST) {
    const allowedNorm = normalizePropertyToken(allowed);
    if (allowedNorm === 'powerstate') continue;
    if (labelNorm === allowedNorm || labelLower.includes(allowed)) return true;
    if (labelNorm.includes(allowedNorm)) return true;
  }

  for (const pattern of AKS_PROPERTY_KEY_PATTERNS) {
    if (pattern === 'powerstate') continue;
    if (keyNorm.includes(pattern)) return true;
  }

  return false;
}

function normalizePropertyToken(value) {
  return String(value || '').trim().toLowerCase().replace(/[._\s-]+/g, '');
}

function propertyValueLooksLikeArmPath(value) {
  const text = String(value || '').trim();
  return ARM_PATH_VALUE_RE.test(text) || text.includes('/providers/');
}

/**
 * True when a property row belongs in the canvas Properties section.
 * Keeps assessment, evidence, and basic operational fields; drops ARM noise and header dupes.
 */
export function isAssessmentProperty(label, key = '', resourceType = '') {
  const labelText = String(label || '').trim();
  const labelLower = labelText.toLowerCase();
  const keyLower = String(key || '').toLowerCase();
  const combined = `${labelLower} ${keyLower}`;

  if (!labelText) return false;
  if (ASSESSMENT_PROPERTY_DENYLIST_RE.test(combined)) return false;
  if (HEADER_DUPLICATE_PROPERTY_LABELS.has(labelLower)) return false;

  const canonicalType = String(resourceType || '').toLowerCase();
  const row = { label: labelText, fact_key: key };

  if (isAksResourceType(canonicalType)) {
    return isAksAllowedProperty(labelText, key);
  }

  if (LIFECYCLE_PROPERTY_RE.test(combined) || CONNECTIVITY_PROPERTY_RE.test(combined)) return true;
  if (SECURITY_PROPERTY_RE.test(combined)) return true;
  if (isAnalysisEssentialRow(row, { canonicalType: canonicalType || undefined })) return true;

  return isMajorProperty({ label: labelText, fact_key: key });
}

export function filterAssessmentPropertyItems(items, resourceType = '') {
  return (items || []).filter((item) => {
    const value = toDisplayText(item?.value);
    if (!value || value === '—') return false;
    if (propertyValueLooksLikeArmPath(value) && !CONNECTIVITY_PROPERTY_RE.test(String(item?.label || ''))) {
      return false;
    }
    return isAssessmentProperty(item?.label, item?.fact_key, resourceType);
  });
}

export function filterAssessmentPropertyGroups(groups, resourceType = '') {
  return (groups || [])
    .map((g) => ({
      ...g,
      items: filterAssessmentPropertyItems(g.items, resourceType),
    }))
    .filter((g) => g.items.length > 0);
}

export function isMajorProperty(item) {
  if (item?.major) return true;
  return MAJOR_PROPERTY_LABELS.has(String(item?.label || '').toLowerCase());
}

export function getVisibleCanvasSections(data, profile) {
  const defaultOrder = [
    'summary', 'properties', 'pools', 'recommendation', 'metrics', 'instances',
    'trends', 'cost', 'insights', 'advisor', 'tags', 'history',
  ];
  const order = profile?.sectionOrder || defaultOrder;
  let tabs = [...(profile?.tabs || INSIGHT_PROFILES.vm.tabs)];
  if (!data.insights) tabs = tabs.filter((t) => t !== 'insights');
  if (!data.advisor?.length) tabs = tabs.filter((t) => t !== 'advisor');
  if (!data.trends?.length) tabs = tabs.filter((t) => t !== 'trends');
  const profileType = data?.profileType || (profile?.tabs?.includes('pools') ? 'kubernetes' : 'vm');
  const metricsLoading = Boolean(data?.metricsLoading);
  if (!data.nodePools?.length && !(metricsLoading && profileType === 'kubernetes')) {
    tabs = tabs.filter((t) => t !== 'pools');
  }
  if (!data.metrics?.length) tabs = tabs.filter((t) => t !== 'metrics');
  const showInstancesWhileLoading = metricsLoading && ['vm', 'vmss'].includes(data?.profileType);
  if (!data.instances?.length && !showInstancesWhileLoading) {
    tabs = tabs.filter((t) => t !== 'instances');
  }

  const allowed = new Set();
  if (tabs.includes('overview')) allowed.add('summary');
  allowed.add('recommendation');
  tabs.forEach((t) => {
    if (t === 'overview' || t === 'recommendations' || t === 'actions') return;
    allowed.add(t);
  });
  if (!data.canvasPropertyGroups?.length) allowed.delete('properties');
  return order.filter((s) => allowed.has(s));
}

const EVIDENCE_GROUP_ORDER = ['utilization', 'cost', 'configuration', 'risk'];

const EVIDENCE_GROUP_LABELS = {
  utilization: 'Utilization',
  cost: 'Cost signals',
  configuration: 'Configuration',
  risk: 'Risk',
};

const PILLAR_TO_EVIDENCE_GROUP = {
  performance: 'utilization',
  cost: 'cost',
  reliability: 'configuration',
  operations: 'configuration',
  data: 'configuration',
  security: 'risk',
  governance: 'risk',
  other: 'configuration',
};

const VISIBLE_EVIDENCE_ROWS = 6;
const MAX_EVIDENCE_ROWS = 8;

const EVIDENCE_METADATA_SKIP = new Set([
  'assessment_file',
  'required_evidence',
  'evidence_rows',
  'evidence_factors',
  'exclude_inventory_facts',
  '_evidence_meta',
  'rule_thresholds',
  'data_quality',
  'engine',
  'rule_source',
  'sub_engine',
  'recommendation_action',
  'pillar',
  'confidence',
  'offer_type',
  'region_count',
  'resource_elements',
  'signals',
  'creation_data',
  'creationData',
  'max_unattached_disk_days',
  'disk_io_idle_bps',
  'disk_idle_min_size_gb',
  'disk_iops_block_downgrade_pct',
  'disk_iops_high_util_pct',
  'disk_throughput_high_util_pct',
  'evaluation_window_days',
  'min_monthly_savings_usd',
  'disk_capacity_used_pct_max',
  'disk_queue_depth_contention',
]);

function isDiskRuleId(ruleId = '') {
  return String(ruleId || '').toUpperCase().startsWith('DISK_');
}

function isCosmosRuleId(ruleId = '') {
  return String(ruleId || '').toUpperCase().startsWith('COSMOS_');
}

function isGovernanceNoiseRule(ruleId = '') {
  const rid = String(ruleId || '').toLowerCase();
  return rid === 'best_unapproved_region' || rid.includes('unapproved_region');
}

function rowsFromStructuredEvidence(evidence) {
  const rows = Array.isArray(evidence?.evidence_rows) ? evidence.evidence_rows : [];
  return rows
    .filter((row) => row?.label && row?.value && row.value !== '—')
    .map((row) => ({
      label: toDisplayText(row.label),
      value: toDisplayText(row.value),
      hint: row.threshold ? `Threshold: ${row.threshold}` : undefined,
      major: row.status === 'fail',
      group: mapPillarToEvidenceGroup(row.pillar || 'performance'),
    }));
}

function mapPillarToEvidenceGroup(pillar) {
  return PILLAR_TO_EVIDENCE_GROUP[pillar] || 'configuration';
}

function rowFromCheck(check) {
  const label = toDisplayText(check?.signal);
  const value = toDisplayText(formatEvidenceCheckValue(check));
  const threshold = formatEvidenceThreshold(check);
  const hint = threshold && threshold !== '—' ? `Threshold: ${threshold}` : undefined;
  return {
    label,
    value,
    hint,
    major: check?.passed === false,
  };
}

function rowFromOptMetric(metric) {
  const hint = metric.status ? optimizationMetricStatusLabel(metric.status) : undefined;
  return {
    label: toDisplayText(metric.label),
    value: toDisplayText(metric.formatted ?? metric.value),
    hint,
    major: ['critical', 'high', 'underutilized', 'low', 'above_threshold'].includes(metric.status),
  };
}

function rowFromTrigger(item) {
  const label = toDisplayText(item.label || item.fact_key);
  const value = toDisplayText(item.value);
  const hintParts = [];
  if (item.threshold) hintParts.push(`Threshold: ${item.threshold}`);
  const effect = item.pillarEffect || item.effect_performance || item.effect_cost;
  if (effect) hintParts.push(toDisplayText(effect));
  return {
    label,
    value: value || '—',
    hint: hintParts.length ? hintParts.join(' · ') : undefined,
    major: false,
  };
}

function buildEvidenceGroupsFromRows(rows) {
  const buckets = {};
  for (const row of rows) {
    const key = row.group || 'configuration';
    if (!buckets[key]) buckets[key] = [];
    buckets[key].push(row);
  }
  return EVIDENCE_GROUP_ORDER
    .filter((key) => buckets[key]?.length)
    .map((key) => ({
      key,
      label: EVIDENCE_GROUP_LABELS[key],
      rows: buckets[key],
    }));
}

/** Single concise rationale sentence — not duplicated in evidence rows. */
export function buildRationale(finding) {
  const evidence = normalizeEvidence(finding?.evidence);
  const summary = toDisplayText(evidence?.summary).trim();
  if (summary && summary !== '—') return summary;

  const detail = toDisplayText(finding?.detail || finding?.recommendation).trim();
  if (detail) {
    const sentences = detail.match(/[^.!?]+[.!?]+/g) || [detail];
    return sentences.slice(0, 2).join(' ').replace(/\s+/g, ' ').trim();
  }
  return topFindingHeadline(finding);
}

/** Structured evidence rows grouped for canvas rendering. */
export function buildEvidenceRows(finding, options = {}) {
  const evidence = normalizeEvidence(finding?.evidence);
  const ruleId = String(finding?.rule_id || '').toUpperCase();
  const rationaleText = options.rationale ?? buildRationale(finding);

  const structuredRows = rowsFromStructuredEvidence(evidence);
  if (structuredRows.length) {
    const capped = structuredRows.slice(0, MAX_EVIDENCE_ROWS);
    const visible = capped.slice(0, VISIBLE_EVIDENCE_ROWS);
    const overflowRows = capped.slice(VISIBLE_EVIDENCE_ROWS);
    return {
      groups: buildEvidenceGroupsFromRows(visible),
      overflowGroups: buildEvidenceGroupsFromRows(overflowRows),
      overflowCount: overflowRows.length,
      totalCount: capped.length,
    };
  }

  if (isDiskRuleId(ruleId) || isCosmosRuleId(ruleId) || isGovernanceNoiseRule(ruleId) || evidence?.exclude_inventory_facts) {
    return {
      groups: [],
      overflowGroups: [],
      overflowCount: 0,
      totalCount: 0,
    };
  }

  const buckets = {
    utilization: [],
    cost: [],
    configuration: [],
    risk: [],
  };
  const seen = new Set();

  const addRow = (group, row) => {
    if (!row?.label || !row.value || row.value === '—') return;
    const dedupeKey = `${row.label}:${row.value}`.toLowerCase();
    if (seen.has(dedupeKey)) return;
    const combined = `${row.label} ${row.value}`;
    if (isDuplicateEvidenceText(combined, rationaleText)) return;
    seen.add(dedupeKey);
    buckets[group].push({ ...row, group });
  };

  const optMetrics = evidence
    ? evidenceOptimizationMetrics(evidence, { hideEngineScores: true, hideEstimatedSavings: true })
    : null;
  const performanceMetrics = (optMetrics?.performance || [])
    .filter((m) => m.status !== 'unavailable');

  let checks = evidence ? evidenceChecks(evidence) : [];
  checks = dedupeChecksAgainstMetrics(checks, performanceMetrics);

  for (const check of checks) {
    if (isInventoryPropertyEvidence(check?.signal, check?.fact_key || check?.value_key)) continue;
    const group = mapPillarToEvidenceGroup(inferCheckPillar(check));
    addRow(group, rowFromCheck(check));
  }

  for (const metric of performanceMetrics) {
    if (isInventoryPropertyEvidence(metric.label, metric.fact_key || metric.id)) continue;
    addRow('utilization', rowFromOptMetric(metric));
  }

  for (const metric of (optMetrics?.cost || [])) {
    if (metric.id === 'estimated_savings') continue;
    addRow('cost', rowFromOptMetric(metric));
  }

  const triggers = Array.isArray(evidence?.trigger_metrics) ? evidence.trigger_metrics : [];
  for (const trigger of triggers) {
    addRow('utilization', rowFromTrigger(trigger));
  }

  const hasStructuredRows = EVIDENCE_GROUP_ORDER.some((key) => buckets[key].length > 0);
  if (!hasStructuredRows && evidence && !evidence.exclude_inventory_facts && !isDiskRuleId(ruleId)) {
    for (const detail of extractResourceTechnicalDetails(evidence).slice(0, MAX_EVIDENCE_ROWS)) {
      if (EVIDENCE_METADATA_SKIP.has(detail.key)) continue;
      if (isInventoryPropertyEvidence(detail.label, detail.key)) continue;
      addRow('configuration', { label: detail.label, value: detail.value });
    }
  }

  const allRows = EVIDENCE_GROUP_ORDER.flatMap((key) => buckets[key]);
  const capped = allRows.slice(0, MAX_EVIDENCE_ROWS);
  const visible = capped.slice(0, VISIBLE_EVIDENCE_ROWS);
  const overflowRows = capped.slice(VISIBLE_EVIDENCE_ROWS);

  return {
    groups: buildEvidenceGroupsFromRows(visible),
    overflowGroups: buildEvidenceGroupsFromRows(overflowRows),
    overflowCount: overflowRows.length,
    totalCount: capped.length,
  };
}

export function pickPrimaryEvidenceMetric(finding, metrics = []) {
  const evidence = normalizeEvidence(finding?.evidence);
  const optMetrics = evidence
    ? evidenceOptimizationMetrics(evidence, { hideEngineScores: true })
    : null;
  const perf = (optMetrics?.performance || []).filter((m) => m.status !== 'unavailable');
  const percentMetric = perf.find((m) => isPercentOptimizationMetric(m));
  if (percentMetric) {
    return {
      label: toDisplayText(percentMetric.label),
      value: toDisplayText(percentMetric.formatted ?? percentMetric.value),
      pct: parseOptimizationPercentValue(percentMetric.formatted, percentMetric.value),
    };
  }
  if (metrics?.length) {
    const m = metrics[0];
    return {
      label: toDisplayText(m.label),
      value: toDisplayText(m.value),
      pct: m.pct ?? null,
    };
  }
  return null;
}

function categorizePropertyRow(row) {
  const label = String(row?.label || '').toLowerCase();
  const key = String(row?.fact_key || '').toLowerCase();
  const combined = `${label} ${key}`;
  if (LIFECYCLE_PROPERTY_RE.test(combined) || label === 'status' || label === 'state') return 'Lifecycle';
  if (CONNECTIVITY_PROPERTY_RE.test(combined)) return 'Connectivity';
  if (SECURITY_PROPERTY_RE.test(combined)) return 'Security';
  return 'Configuration';
}

function nestedGroupCategory(groupLabel) {
  const label = String(groupLabel || '').toLowerCase();
  if (/network|ip config|connectivity/.test(label)) return 'Connectivity';
  if (/encrypt|security/.test(label)) return 'Security';
  return null;
}

/** Collapse status/state/power-state variants to one dedupe token. */
const PROPERTY_LABEL_DEDUPE_ALIASES = {
  status: 'power state',
  state: 'power state',
  powerstate: 'power state',
  'power state': 'power state',
  diskstate: 'disk state',
  'disk state': 'disk state',
};

export function normalizePropertyLabelForDedupe(label = '') {
  const key = String(label || '').trim().toLowerCase();
  return PROPERTY_LABEL_DEDUPE_ALIASES[key] || key;
}

/** Keep the first row per normalized label (case-insensitive). */
export function dedupePropertyItemsByLabel(items = [], seen = null) {
  const globalSeen = seen || new Set();
  return (items || []).filter((item) => {
    const value = toDisplayText(item?.value);
    if (!value || value === '—') return false;
    const key = normalizePropertyLabelForDedupe(item.label);
    if (!key) return true;
    if (globalSeen.has(key)) return false;
    globalSeen.add(key);
    return true;
  });
}

function dedupePropertyItems(items) {
  return dedupePropertyItemsByLabel(items);
}

/** Dedupe property items across all groups — first occurrence wins (top to bottom). */
export function dedupePropertyGroupsByLabel(groups = []) {
  const seen = new Set();
  return (groups || [])
    .map((group) => ({
      ...group,
      items: dedupePropertyItemsByLabel(group.items, seen),
    }))
    .filter((group) => group.items.length > 0);
}

/** Dedupe drawer property rows across groups — same label alias rules as canvas. */
export function dedupeDrawerPropertyGroups(groups = []) {
  const seen = new Set();
  return (groups || [])
    .map((group) => ({
      ...group,
      rows: (group.rows || []).filter((row) => {
        const value = toDisplayText(row.value ?? row.formatted);
        if (!value || value === '—') return false;
        const key = normalizePropertyLabelForDedupe(row.label);
        if (!key) return true;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      }),
    }))
    .filter((group) => group.rows.length > 0);
}

function drawerRowToCanvasItem(row) {
  return {
    label: row.label,
    value: toDisplayText(row.formatted ?? row.value),
    major: isMajorProperty({ label: row.label, fact_key: row.fact_key }),
    fact_key: row.fact_key,
  };
}

function buildCanvasPropertyGroupsFromResource(resource, inventoryProperties = []) {
  if (!resource) return [];

  const resourceType = resolveDrawerCanonicalType(resource);
  const drawerGroups = buildResourcePropertyGroups(resource, inventoryProperties);
  const buckets = new Map(CANVAS_PROPERTY_CATEGORY_ORDER.map((title) => [title, []]));
  const nestedGroups = [];

  const addItem = (category, item) => {
    if (!isAssessmentProperty(item.label, item.fact_key, resourceType)) return;
    if (!buckets.has(category)) buckets.set(category, []);
    buckets.get(category).push(item);
  };

  const stateValue = resource.state || resource.properties?.diskState || resource.properties?.powerState;
  if (stateValue) {
    addItem('Lifecycle', { label: 'State', value: formatPowerState(stateValue), major: true });
  }

  for (const group of drawerGroups) {
    const rows = filterDisplayablePropertyRows(group.rows || []);
    if (!rows.length) continue;

    if (group.id === 'prop:general') {
      for (const row of rows) {
        addItem(categorizePropertyRow(row), drawerRowToCanvasItem(row));
      }
      continue;
    }

    const category = nestedGroupCategory(group.label);
    if (category) {
      for (const row of rows) addItem(category, drawerRowToCanvasItem(row));
    } else {
      const items = rows
        .map(drawerRowToCanvasItem)
        .filter((item) => isAssessmentProperty(item.label, item.fact_key, resourceType));
      if (items.length) {
        nestedGroups.push({ title: group.label, items });
      }
    }
  }

  const result = CANVAS_PROPERTY_CATEGORY_ORDER
    .filter((title) => buckets.get(title)?.length)
    .map((title) => ({
      title,
      items: dedupePropertyItems(buckets.get(title)),
    }));

  for (const nested of nestedGroups) {
    const items = dedupePropertyItems(nested.items);
    if (items.length) result.push({ title: nested.title, items });
  }

  return result;
}

function normalizePrebuiltPropertyGroups(groups) {
  return (groups || []).map((g) => ({
    title: g.title || g.name || 'Properties',
    items: dedupePropertyItems((g.items || g.properties || []).map((item) => ({
      label: item.label || item.name,
      value: toDisplayText(item.value ?? item.display),
      major: item.major || isMajorProperty(item),
    }))),
  })).filter((g) => g.items.length > 0);
}

function resolveResourceForProperties(propertiesPayload, row) {
  if (propertiesPayload?.resource) {
    return {
      ...(row || {}),
      ...propertiesPayload.resource,
      properties: {
        ...(row?.properties || {}),
        ...(propertiesPayload.resource.properties || {}),
      },
      tags: propertiesPayload.resource.tags || row?.tags,
    };
  }
  if (row) return row;
  return null;
}

export function buildPropertyGroups(propertiesPayload, row = null) {
  const prebuilt = propertiesPayload?.groups || propertiesPayload?.property_groups;
  if (Array.isArray(prebuilt) && prebuilt.length) {
    return normalizePrebuiltPropertyGroups(prebuilt);
  }

  const flat = propertiesPayload?.properties || propertiesPayload?.items;
  if (Array.isArray(flat) && flat.length) {
    const resourceType = resolveDrawerCanonicalType(row);
    return [{
      title: 'Configuration',
      items: filterAssessmentPropertyItems(
        dedupePropertyItems(flat.map((item) => ({
          label: item.label || item.name || item.key,
          value: toDisplayText(item.value ?? item.display),
          major: isMajorProperty(item),
          fact_key: item.fact_key || item.key,
        }))),
        resourceType,
      ),
    }].filter((g) => g.items.length > 0);
  }

  const resource = resolveResourceForProperties(propertiesPayload, row);
  const inventoryProperties = propertiesPayload?.inventory_properties || [];
  if (resource) {
    const resourceType = resolveDrawerCanonicalType(resource);
    if (resourceType === 'compute/disk') {
      const props = { ...(resource.properties || {}), ...(row?.properties || {}) };
      if (resource.sku && !props.sku) {
        props.sku = typeof resource.sku === 'object' ? resource.sku.name : resource.sku;
      }
      return buildDiskPropertyGroups({ properties: props }).map((g) => ({
        title: g.title,
        items: g.items.map((item) => ({
          label: item.label,
          value: toDisplayText(item.value),
          major: item.major,
        })),
      }));
    }
    return buildCanvasPropertyGroupsFromResource(resource, inventoryProperties);
  }

  return [];
}

export function collectSkuSpecLabels(sku) {
  const labels = new Set();
  [sku?.current?.specs, sku?.target?.specs].forEach((specs) => {
    (specs || []).forEach((s) => labels.add(String(s.label).toLowerCase()));
  });
  return labels;
}

function collectSkuPanelValues(sku) {
  const values = new Set();
  const current = sku?.current || {};
  [current.name, current.tier, current.size, current.region].forEach((v) => {
    if (v && v !== '—') values.add(String(v).toLowerCase());
  });
  (current.specs || []).forEach((s) => {
    if (s?.value) values.add(String(s.value).toLowerCase());
  });
  return values;
}

/**
 * Remove SKU-panel-owned performance/pricing rows from canvas properties.
 * Falls back to full groups (minus exact label+value duplicates) when filter would empty the section.
 */
export function filterCanvasPropertyGroups(groups, sku) {
  const specLabels = collectSkuSpecLabels(sku);
  const pricingLabels = SKU_PANEL_PRICING_LABELS;

  const primaryFilter = (item) => {
    const label = String(item.label || '').toLowerCase();
    const factKey = String(item.fact_key || '').toLowerCase();
    const combined = `${label} ${factKey}`;
    if (LIFECYCLE_PROPERTY_RE.test(combined) || CONNECTIVITY_PROPERTY_RE.test(combined)) return true;
    if (specLabels.has(label) || SKU_PANEL_SPEC_LABELS.has(label)) return false;
    if (pricingLabels.has(label)) return false;
    return true;
  };

  let filtered = (groups || []).map((g) => ({
    ...g,
    items: (g.items || []).filter(primaryFilter),
  })).filter((g) => g.items.length > 0);

  if (!filtered.length && groups?.length) {
    const skuValues = collectSkuPanelValues(sku);
    filtered = groups.map((g) => ({
      ...g,
      items: (g.items || []).filter((item) => {
        const label = String(item.label || '').toLowerCase();
        const value = String(item.value || '').toLowerCase();
        if (specLabels.has(label) && skuValues.has(value)) return false;
        if (pricingLabels.has(label)) return false;
        return true;
      }),
    })).filter((g) => g.items.length > 0);
  }

  return filtered;
}

export function resolveCanvasPropertyGroups(propertyGroups, sku, resourceType = '') {
  const canonical = String(resourceType || '').toLowerCase();
  if (canonical === 'compute/disk') {
    return dedupePropertyGroupsByLabel(propertyGroups || []);
  }

  const skuFiltered = filterCanvasPropertyGroups(propertyGroups, sku);
  const base = skuFiltered.length ? skuFiltered : (propertyGroups || []);
  const assessmentFiltered = filterAssessmentPropertyGroups(base, resourceType);
  const resolved = assessmentFiltered.length ? assessmentFiltered : base;
  return organizePropertyGroupsForDisplay(dedupePropertyGroupsByLabel(resolved));
}

/**
 * Flatten property groups into one continuous 2-column grid.
 * Removes subgroup titles and empty groups so items pack without grid holes.
 */
export function organizePropertyGroupsForDisplay(groups = []) {
  const nonEmpty = (groups || []).filter((g) => (g.items || []).length > 0);
  if (!nonEmpty.length) return [];

  const items = nonEmpty.flatMap((g) => g.items);
  if (!items.length) return [];

  return [{ title: '', items, flat: true }];
}

/** Flatten drawer property groups into one full-width card (no card-grid holes). */
export function organizeDrawerPropertyGroupsForDisplay(groups = []) {
  const nonEmpty = (groups || []).filter((g) => (g.rows || []).length > 0);
  if (!nonEmpty.length) return [];

  const rows = nonEmpty.flatMap((g) => g.rows);
  if (!rows.length) return [];

  return [{
    id: 'prop:display',
    label: '',
    rows,
    flat: true,
    spanFull: true,
  }];
}

function metricRowToCanvasItem(row) {
  const normalized = normalizeMetricRow(row);
  const factKey = normalized.fact_key || normalized.metric_name;
  const label = labelForFactKey(factKey, normalized.label);
  const stats = normalized.stats || {};
  const raw = stats.average ?? stats.maximum ?? normalized.value;
  const value = formatFactValue(factKey, raw, normalized.unit);
  let pct = null;
  if (raw != null && (String(factKey).includes('pct') || String(normalized.unit).includes('%'))) {
    const num = Number(raw);
    if (Number.isFinite(num)) pct = Math.min(100, Math.max(0, num));
  }
  return { label, value: toDisplayText(value), pct, fact_key: factKey };
}

export function buildCanvasMetrics(metricsData) {
  if (!metricsData) return [];
  const rows = [
    ...(metricsData.metrics || []),
    ...(metricsData.derived || []),
  ];
  return rows
    .map(metricRowToCanvasItem)
    .filter((m) => m.label && m.value && m.value !== '—');
}

function extractInstanceMetricValue(instance, factKeys = []) {
  const detail = instance?.metrics_detail || instance?.metrics || [];
  for (const row of detail) {
    const key = String(row?.fact_key || '').toLowerCase();
    if (!factKeys.some((k) => key === k || key.includes(k))) continue;
    const val = row?.stats?.average ?? row?.stats?.maximum ?? row?.value;
    if (val != null) return val;
  }
  return null;
}

function formatInstanceMetric(value, factKey, unavailable = false) {
  if (unavailable) return 'Metrics unavailable';
  if (value == null) return '—';
  return formatFactValue(factKey, value, '%');
}

export function buildCanvasInstances(metricsData, row = null, { metricsError = false } = {}) {
  const unavailable = Boolean(metricsError);
  const rawInstances = metricsData?.instances || [];
  if (rawInstances.length) {
    return rawInstances.map((instance) => {
      const normalized = normalizePoolInstance(instance);
      const cpu = normalized.cpuPct ?? extractInstanceMetricValue(instance, ['avg_cpu_pct', 'cpu', 'node_cpu_pct']);
      const mem = normalized.memPct ?? extractInstanceMetricValue(instance, ['avg_mem_pct', 'avg_memory_pct', 'memory', 'node_mem_pct']);
      const network = extractInstanceMetricValue(instance, ['network_in', 'network_out', 'network']);
      return {
        name: normalized.name,
        size: toDisplayText(instance.vm_size || instance.vmSize || row?.properties?.hardwareProfile?.vmSize),
        powerState: formatPowerState(normalized.powerState),
        zone: toDisplayText(instance.zone || instance.availability_zone),
        cpu: formatInstanceMetric(cpu, 'avg_cpu_pct', unavailable && cpu == null),
        memory: formatInstanceMetric(mem, 'avg_mem_pct', unavailable && mem == null),
        network: network != null ? formatFactValue('network_in', network) : null,
        cpuPct: cpu,
        memPct: mem,
        metricsUnavailable: unavailable && cpu == null && mem == null,
      };
    });
  }

  const arm = String(row?.id || row?.resource_id || '').toLowerCase();
  if (!arm.includes('/virtualmachines/') || arm.includes('/virtualmachinescalesets/')) {
    return [];
  }

  const cpu = extractInstanceMetricValue({ metrics_detail: metricsData?.metrics_detail || metricsData?.metrics }, ['avg_cpu_pct']);
  const mem = extractInstanceMetricValue({ metrics_detail: metricsData?.metrics_detail || metricsData?.metrics }, ['avg_mem_pct', 'avg_memory_pct']);
  if (cpu == null && mem == null) return [];

  return [{
    name: row?.name || 'Instance',
    size: toDisplayText(row?.properties?.hardwareProfile?.vmSize || row?.sku),
    powerState: formatPowerState(row?.properties?.powerState || row?.state),
    zone: toDisplayText(row?.properties?.availabilityZone || row?.zone),
    cpu: formatInstanceMetric(cpu, 'avg_cpu_pct', unavailable && cpu == null),
    memory: formatInstanceMetric(mem, 'avg_mem_pct', unavailable && mem == null),
    network: null,
    cpuPct: cpu,
    memPct: mem,
    metricsUnavailable: unavailable && cpu == null && mem == null,
  }];
}

export function buildCanvasNodePools(row, metricsData = null) {
  if (!row) return [];
  const aksApiPath = apiPathForCanonical('containers/aks');
  const enriched = enrichDrawerResource(row, { apiPath: aksApiPath, metricsData });
  if (enriched?._pools?.length) return enriched._pools;

  const normalized = normalizeAksCluster(row);
  if (!normalized._pools?.length) return row?.nodePools || [];

  const clusterName = normalized.name || '';
  const poolsWithUtil = aggregatePoolUtilization(
    clusterName,
    normalized._pools,
    metricsData?.instances || [],
    metricsData?.facts || {},
    metricsData?.pool_metrics || [],
  );
  return attachPoolInstances(poolsWithUtil, metricsData?.pool_metrics || []);
}

function resolveInsightProfileType(row, finding) {
  const service = String(serviceDisplayNameForRow(row) || finding?.resource_type || '').toLowerCase();
  const arm = String(row?.id || row?.resource_id || finding?.resource_id || '').toLowerCase();
  if (service.includes('kubernetes') || arm.includes('/managedclusters/')) return 'kubernetes';
  if (arm.includes('/virtualmachinescalesets/') && !arm.includes('/virtualmachines/')) return 'vmss';
  if (service.includes('virtual machine') || arm.includes('/virtualmachines/')) return 'vm';
  if (service.includes('disk') || arm.includes('/disks/')) return 'disk';
  if (service.includes('database') || arm.includes('/sql/') || arm.includes('/documentdb/')) return 'database';
  if (service.includes('storage') || arm.includes('/storageaccounts/')) return 'storage';
  return 'vm';
}

function buildTrendRows(analysis) {
  const trends = analysis?.trends;
  if (!trends) return [];
  const rows = [];
  if (trends.cpu_trend) {
    rows.push({
      label: 'CPU trend',
      value: toDisplayText(trends.cpu_trend.slope || trends.cpu_trend.label || '—'),
      tone: trends.cpu_trend.slope === 'increasing' ? 'warn' : 'muted',
    });
  }
  if (trends.memory_trend) {
    rows.push({
      label: 'Memory trend',
      value: toDisplayText(trends.memory_trend.slope || trends.memory_trend.label || '—'),
      tone: trends.memory_trend.slope === 'increasing' ? 'warn' : 'muted',
    });
  }
  if (trends.cost_vs_prev_month_pct != null) {
    rows.push({
      label: 'Cost vs prior month',
      value: `${trends.cost_vs_prev_month_pct}%`,
      tone: trends.cost_vs_prev_month_pct > 0 ? 'warn' : 'muted',
    });
  }
  return rows;
}

function buildSkuFromFinding(finding, row, cost, savings) {
  const target = finding?.recommended_sku || finding?.target_sku || finding?.target_tier;
  const current = finding?.current_sku || row?.sku || row?.properties?.sku;
  const changeType = formatCategoryLabel(finding?.category || 'Change');
  const targetCost = Math.max(0, cost - savings);

  const currentName = toDisplayText(
    current?.name || current || row?.properties?.vmSize || 'Current',
  );

  return {
    changeType,
    current: {
      name: currentName,
      tier: toDisplayText(current?.tier),
      size: toDisplayText(current?.size),
      region: humanizeAzureRegion(row?.location || row?.region) || '—',
      specs: [],
      monthlyCost: cost,
    },
    target: target ? {
      name: toDisplayText(typeof target === 'string' ? target : (target.name || 'Recommended')),
      tier: toDisplayText(target?.tier),
      size: toDisplayText(target?.size),
      region: humanizeAzureRegion(row?.location || row?.region) || '—',
      specs: [],
      monthlyCost: targetCost,
    } : null,
  };
}

function attachRecommendationItems(data, findings = [], context = {}) {
  if (!data) return data;
  const sorted = sortFindingsByPriority((findings || []).filter(Boolean));
  if (!sorted.length) return data;

  data.recommendationItems = buildRecommendationsPanelModel(sorted, context);
  if (data.recommendationItems.length > 1) {
    const totalSavings = data.recommendationItems.reduce(
      (sum, item) => sum + (Number(item.savings) || 0),
      0,
    );
    data.savings = totalSavings;
    data.recTitle = `${data.title || 'Resource'} — ${data.recommendationItems.length} recommendations`;
    if (data.costBreakdown) {
      const current = data.costBreakdown.current || data.cost || 0;
      data.costBreakdown.savings = totalSavings;
      data.costBreakdown.projected = Math.max(0, current - totalSavings);
    }
  }
  return data;
}

/** Build insight canvas model from API payloads. Gaps filled with derived/mock fields (see comments). */
export function buildInsightData({
  finding,
  findings = [],
  row,
  actions = [],
  propertiesPayload = null,
  advisorItems = [],
  metricsData = null,
  advancedAnalysis = null,
  metrics = [],
  trends = [],
  metricsLoading = false,
  metricsError = false,
  metricsTimespan = 'P7D',
  subscriptionLabel = '',
  subscriptionId = '',
  resourceId = '',
  currency = 'CAD',
  analyzedAt = null,
}) {
  const resolvedFindings = (findings?.length ? findings : (finding ? [finding] : []));
  const profileType = resolveInsightProfileType(row, finding);
  if (profileType === 'disk') {
    const mergedRow = row || {
      id: finding?.resource_id,
      name: finding?.resource_name,
      resource_group: finding?.resource_group,
      location: finding?.location,
      type: 'Microsoft.Compute/disks',
      properties: propertiesPayload?.resource?.properties || {},
    };
    if (!mergedRow.id && !finding?.resource_id) return null;
    const metrics = { ...(mergedRow.metrics || mergedRow._metrics || {}) };
    if (metricsData?.derived?.length) {
      for (const item of metricsData.derived) {
        const key = item.fact_key;
        const val = item.stats?.maximum ?? item.stats?.average ?? item.value;
        if (key && val != null) metrics[key] = val;
      }
    }
    mergedRow.metrics = metrics;
    mergedRow._metrics = metrics;
    if (propertiesPayload?.resource) {
      const res = propertiesPayload.resource;
      mergedRow.properties = {
        ...(res.properties || {}),
        ...(mergedRow.properties || {}),
      };
      mergedRow.assessment_properties = {
        ...(res.assessment_properties || {}),
        ...(mergedRow.assessment_properties || {}),
      };
      mergedRow.property_rows = mergedRow.property_rows
        || res.property_rows
        || res.assessment_property_rows
        || [];
      if (res.cost && typeof res.cost === 'object' && !mergedRow.cost) {
        mergedRow.cost = res.cost;
      }
    }
    return attachRecommendationItems(
      buildDiskInsightFromApi({
        row: mergedRow,
        finding,
        findingsByResource: null,
        analyzedAt,
        subscriptionLabel,
      }),
      resolvedFindings,
      { row: mergedRow, metrics: mergedRow.metrics },
    );
  }

  const profile = INSIGHT_PROFILES[profileType] || INSIGHT_PROFILES.vm;
  const canonicalType = resolveDrawerCanonicalType(row) || profileType;
  const workflowKey = resolveWorkflowStatus(actions);
  const workflow = workflowKey.charAt(0).toUpperCase() + workflowKey.slice(1);
  const severity = mapSeverityChip(finding?.severity);
  const severityLabel = severity.charAt(0).toUpperCase() + severity.slice(1);
  const sourceKey = mapSourceChip(finding);
  const sourceLabels = { engine: 'Engine', advisor: 'Advisor', governance: 'Governance' };
  const cost = row ? resourceBilledMtd(row) : 0;
  const retailMonthly = row ? resourceRetailMonthly(row) : 0;
  const savings = Number(
    finding?.estimated_monthly_savings_usd
    ?? finding?.monthly_savings_usd
    ?? finding?.savings_usd
    ?? 0,
  );
  const savingsPct = cost > 0 ? Math.round((savings / cost) * 100) : 0;
  const propertyGroups = buildPropertyGroups(propertiesPayload, row);
  const sku = buildSkuFromFinding(finding, row, cost, savings);
  const canvasPropertyGroups = resolveCanvasPropertyGroups(propertyGroups, sku, canonicalType);
  const canvasMetrics = buildCanvasMetrics(metricsData);
  const resolvedMetrics = metrics.length ? metrics : canvasMetrics;
  const nodePools = buildCanvasNodePools(row, metricsData);
  const instances = buildCanvasInstances(metricsData, row, { metricsError });
  const resolvedTrends = trends.length ? trends : buildTrendRows(advancedAnalysis);
  const iconKey = iconForRow(row || { type: finding?.resource_type }, { apiPath: INVENTORY_API_PATH });
  const rationale = buildRationale(finding);
  const evidenceData = buildEvidenceRows(finding, { rationale });
  let ruleEvidence = [];
  let evidenceFactors = [];
  if (isDiskRuleId(finding?.rule_id)) {
    const metricsMap = { ...(row?.metrics || row?._metrics || {}) };
    if (metricsData?.derived?.length) {
      for (const item of metricsData.derived) {
        const key = item.fact_key;
        const val = item.stats?.maximum ?? item.stats?.average ?? item.value;
        if (key && val != null) metricsMap[key] = val;
      }
    }
    ruleEvidence = buildRuleEvidence(
      {
        finding: { rule_id: finding?.rule_id, evidence: finding?.evidence },
        metrics: metricsMap,
        properties: row?.properties || propertiesPayload?.resource?.properties || {},
      },
      finding?.evidence,
    );
    const normalizedEvidence = normalizeEvidence(finding?.evidence);
    evidenceFactors = normalizedEvidence?.evidence_factors || [];
  }
  const primaryEvidenceMetric = pickPrimaryEvidenceMetric(finding, resolvedMetrics);
  const costBlock = resourceCostBlock(row);
  const costEnvelope = null;

  const data = {
    profileType,
    profile,
    canonicalType,
    resourceId: resourceId || row?.id || row?.resource_id || finding?.resource_id || '',
    subscriptionId,
    iconKey,
    title: row?.name || finding?.resource_name || 'Resource',
    type: serviceDisplayNameForRow(row) || finding?.resource_type || 'Resource',
    rg: row?.resource_group || finding?.resource_group || '—',
    sub: subscriptionLabel || 'Subscription',
    workflow,
    workflowKey,
    state: formatPowerState(
      row?.properties?.powerState
      || row?.properties?.diskState
      || row?.properties?.provisioningState,
    ),
    recTitle: topFindingHeadline(finding),
    text: rationale,
    rationale,
    rule: toDisplayText(finding?.rule_id || finding?.rule_name),
    source: sourceLabels[sourceKey] || 'Engine',
    sourceKey,
    severity: severityLabel,
    severityKey: severity,
    category: formatCategoryLabel(finding?.category || 'OTHER'),
    cost,
    billedMtd: cost,
    retailMonthly,
    savings,
    savingsPct,
    payback: savings > 0 ? 'Immediate' : '—',
    costTrend: 0, // API gap — no month-over-month trend on resource detail yet
    region: humanizeAzureRegion(row?.location || row?.region) || '—',
    evidenceGroups: evidenceData.groups,
    evidenceOverflowGroups: evidenceData.overflowGroups,
    evidenceOverflowCount: evidenceData.overflowCount,
    ruleEvidence,
    evidenceFactors,
    primaryEvidenceMetric,
    tags: Object.entries(row?.tags || {}).map(([k, v]) => `${k}: ${v}`),
    propertyGroups,
    canvasPropertyGroups,
    sku,
    costBreakdown: {
      current: retailMonthly || cost,
      projected: Math.max(0, (retailMonthly || cost) - savings),
      savings,
      items: savings > 0
        ? [{
          label: 'Monthly cost',
          current: retailMonthly || cost,
          projected: Math.max(0, (retailMonthly || cost) - savings),
        }]
        : [],
      billedMtd: cost,
      retailMonthly: retailMonthly || cost,
      retailSource: costBlock?.retail_source || 'azure_retail_prices',
    },
    costEnvelope,
    costFieldLabels: null,
    insights: advancedAnalysis?.insights || finding?.insights || null,
    advisor: (advisorItems || []).map((a) => ({
      title: a.short_description || a.description || a.title || 'Advisor recommendation',
      impact: a.impact || a.level || 'Medium',
    })),
    metrics: resolvedMetrics,
    trends: resolvedTrends,
    nodePools,
    instances,
    metricsLoading,
    metricsError,
    metricsTimespan,
    related: (finding?.related_findings || []).map((r) => ({
      title: r.title || r.rule_name || 'Related finding',
      sev: mapSeverityChip(r.severity),
    })),
    analyzed: analyzedAt ? formatDateTime(analyzedAt) : '—',
    prevAction: actions[0]?.last_action_label || 'None — first review',
    created: finding?.created_at ? formatDateTime(finding.created_at) : '—',
    timeline: [
      analyzedAt ? `<strong>${formatDateTime(analyzedAt)}</strong> — Analysis refreshed` : null,
      finding?.created_at ? `<strong>${formatDateTime(finding.created_at)}</strong> — Finding created` : null,
    ].filter(Boolean),
    currency,
    finding,
    row,
    actions,
  };

  data.sections = getVisibleCanvasSections(data, profile);
  return attachRecommendationItems(data, resolvedFindings, {
    row,
    metrics: row?.metrics || row?._metrics,
    properties: row?.properties,
  });
}

export function formatInsightCurrency(amount, currency = 'CAD', decimals = 0) {
  return formatCurrency(amount, { currency, decimals });
}

export function skuBadgeClass(changeType) {
  const key = String(changeType || '').toLowerCase().replace(/\s+/g, '-');
  const map = {
    'right-size': 'right-size',
    rightsize: 'right-size',
    downgrade: 'downgrade',
    'tier-change': 'tier-change',
    tier: 'tier-change',
    delete: 'delete',
    idle: 'idle',
    deallocate: 'deallocate',
  };
  return `ic-sku-badge--${map[key] || 'right-size'}`;
}

export function isSkuDeleteAction(sku) {
  const ct = String(sku?.changeType || '').toLowerCase();
  const tn = String(sku?.target?.name || '').toLowerCase();
  return ct === 'delete' || tn.includes('delete resource') || (sku?.target == null && ct === 'delete');
}

export function shouldShowTargetSku(sku) {
  if (isSkuDeleteAction(sku)) return false;
  const target = sku?.target;
  if (!target?.name || target.name === '—') return false;
  return true;
}
