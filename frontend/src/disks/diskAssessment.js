/**
 * Disk assessment v2 — schema bindings from data/disk-assessment.json only.
 * Mirrors design/concept-v2/js/disks/index.js constants.
 */

import assessment from './data/disk-assessment.json';

export const SCHEMA_PATH = 'data/disk-assessment.json';
export const SCHEMA_VERSION = assessment.schema_version || '2.0';
export const DISK_ASSESSMENT = assessment;

export const GROUP_TITLE_MAP = {
  configuration: 'Disk',
  capacity: 'Provisioned capacity',
  attachment: 'Compute host',
  security: 'Security',
};

export const PROPERTY_GROUP_ORDER = ['configuration', 'capacity', 'attachment', 'security'];

/** List columns — configuration fields (concept v2 DISK_LIST_COLUMNS). */
export const DISK_LIST_COLUMNS = [
  { group: 'configuration', armPath: 'properties.diskSizeGB', key: 'diskSizeGB', label: 'Disk size', type: 'size' },
  { group: 'configuration', armPath: 'sku.name', key: 'sku', label: 'SKU', type: 'sku' },
  { group: 'configuration', armPath: 'properties.tier', key: 'tier', label: 'Performance tier', type: 'text' },
  { group: 'configuration', armPath: 'properties.diskState', key: 'diskState', label: 'Disk state', type: 'state' },
  { group: 'attachment', armPath: 'properties.managedBy', key: 'managedBy', label: 'Attached to', type: 'attachment' },
  { group: 'configuration', armPath: 'properties.provisioningState', key: 'provisioningState', label: 'Provisioning state', type: 'text' },
];

export const DISK_LIST_LOCATION = { key: 'region', label: 'Region', type: 'location' };

export const DISK_LIST_METRICS = [
  { factKey: 'disk_iops_utilization_pct', label: 'IOPS utilization', unit: '%' },
  { factKey: 'disk_throughput_utilization_pct', label: 'Throughput utilization', unit: '%' },
];

export const DISK_CANVAS_METRICS = [
  { factKey: 'disk_iops_utilization_pct', label: 'IOPS utilization', unit: '%' },
  { factKey: 'disk_throughput_utilization_pct', label: 'Throughput utilization', unit: '%' },
  { factKey: 'disk_queue_depth', label: 'Queue depth', unit: '' },
  { factKey: 'disk_used_pct', label: 'Capacity used', unit: '%' },
];

export function diskGroupTitle(groupKey) {
  return GROUP_TITLE_MAP[groupKey] || groupKey;
}

export function diskCostFieldLabel(field) {
  const match = (assessment.cost_management?.fields || []).find((f) => f.field === field);
  return match?.label || field;
}

export function getRuleById(ruleId) {
  const id = String(ruleId || '').trim();
  if (!id) return null;
  const rules = assessment.rules || [];
  return rules.find((r) => r.rule_id === id)
    || rules.find((r) => r.rule_id === id.replace(/_EXTENDED$/, ''))
    || null;
}

export function getRuleEvidenceDef(ruleId) {
  const rule = getRuleById(ruleId);
  if (!rule) return null;
  return {
    evidence_factors: rule.evidence_factors || [],
    required_evidence: rule.required_evidence || [],
  };
}

/** Alias for assessment rule evidence contract lookup. */
export function getRuleEvidence(ruleId) {
  return getRuleEvidenceDef(ruleId);
}

const THRESHOLD_DISPLAY = {
  disk_io_idle_bps: '1,024 B/s',
  max_unattached_disk_days: '30 days',
  disk_iops_high_util_pct: '50%',
  disk_capacity_low_pct: '30%',
  capacity_used_pct_max: '30%',
  disk_queue_depth_contention: '10',
};

export function thresholdLabel(thresholdKey) {
  if (!thresholdKey) return '—';
  if (THRESHOLD_DISPLAY[thresholdKey]) return THRESHOLD_DISPLAY[thresholdKey];
  const raw = assessment.optimization_thresholds?.[thresholdKey];
  if (raw == null) return '—';
  if (String(thresholdKey).includes('_pct')) return `${raw}%`;
  if (String(thresholdKey).includes('_bps')) return `${Number(raw).toLocaleString()} B/s`;
  if (String(thresholdKey).includes('_days')) return `${raw} days`;
  return String(raw);
}

export function assessmentPropertyByArmPath(armPath) {
  for (const group of assessment.azure_properties?.groups || []) {
    for (const prop of group.properties || []) {
      if (prop.arm_path === armPath) return prop;
    }
  }
  return null;
}

export const diskAssessmentPropertyByArmPath = assessmentPropertyByArmPath;

export function diskAssessmentPropertyGroupDefs() {
  return (assessment.azure_properties?.groups || []).map((group) => ({
    ...group,
    title: GROUP_TITLE_MAP[group.group] || group.group,
  }));
}

export function diskAssessmentMetricLabel(factKey) {
  const metrics = assessment.azure_metrics?.metrics || [];
  const direct = metrics.find((m) => m.fact_key === factKey);
  if (direct?.metric_name) {
    return direct.metric_name.replace(/^Composite Disk /i, '').replace(/ Bytes\/sec$/i, ' throughput');
  }
  const derived = assessment.azure_metrics?.derived_metrics?.[factKey];
  if (derived) {
    if (factKey === 'disk_iops_utilization_pct') return 'IOPS utilization';
    if (factKey === 'disk_throughput_utilization_pct') return 'Throughput utilization';
    if (factKey === 'disk_queue_depth') return 'Queue depth';
    if (factKey === 'disk_used_pct') return 'Capacity used';
    return factKey.replace(/_/g, ' ');
  }
  return null;
}
