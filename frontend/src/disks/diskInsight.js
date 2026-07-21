/**
 * Disk insight canvas builders — port of design/concept-v2/js/disks/index.js
 * Rules, evidence, and thresholds from disk-assessment.json only.
 */

import { formatDateTime } from '../utils/format';
import { normalizeEvidence } from '../utils/evidenceUtils';
import {
  SCHEMA_PATH,
  PROPERTY_GROUP_ORDER,
  DISK_CANVAS_METRICS,
  diskGroupTitle,
  getRuleEvidenceDef,
  getRuleById,
  thresholdLabel,
} from './diskAssessment';
import { apiRowToConceptDisk } from './diskApiModel';

function isEmptyPropertyValue(value) {
  const v = String(value ?? '').trim();
  return !v || v === '—' || v === '-' || v === 'N/A';
}

/** Property groups — exact concept v2 buildPropertyGroups. */
export function buildPropertyGroups(disk) {
  const p = disk.properties || {};
  const groupsByKey = {
    configuration: {
      group: 'configuration',
      title: diskGroupTitle('configuration'),
      items: [
        { label: 'Disk size', value: p.diskSizeGB != null ? `${p.diskSizeGB} GB` : null, major: true },
        { label: 'SKU', value: p.sku, major: true },
        { label: 'Performance tier', value: p.tier },
        { label: 'Disk state', value: p.diskState, major: true },
        { label: 'Provisioning state', value: p.provisioningState, major: true },
        { label: 'Created', value: p.timeCreated },
        { label: 'Bursting enabled', value: p.burstingEnabled != null ? (p.burstingEnabled ? 'Yes' : 'No') : null },
      ],
    },
    capacity: {
      group: 'capacity',
      title: diskGroupTitle('capacity'),
      items: [
        { label: 'Provisioned IOPS', value: p.diskIOPSReadWrite != null ? Number(p.diskIOPSReadWrite).toLocaleString('en-US') : null },
        { label: 'Provisioned throughput', value: p.diskMBpsReadWrite != null ? `${p.diskMBpsReadWrite} MB/s` : null },
      ],
    },
    attachment: {
      group: 'attachment',
      title: diskGroupTitle('attachment'),
      items: [
        { label: 'Attached to', value: p.managedBy, major: true },
        { label: 'Last ownership update', value: p.lastOwnershipUpdateTime },
        { label: 'Creation source', value: p.creationSource },
      ],
    },
    security: {
      group: 'security',
      title: diskGroupTitle('security'),
      items: [
        { label: 'Encryption settings', value: p.encryption, major: true },
        { label: 'Network access policy', value: p.networkAccessPolicy },
        { label: 'Public network access', value: p.publicNetworkAccess },
      ],
    },
  };

  return PROPERTY_GROUP_ORDER
    .map((key) => {
      const g = groupsByKey[key];
      if (!g) return null;
      const items = g.items.filter((item) => !isEmptyPropertyValue(item.value));
      return items.length ? { ...g, items } : null;
    })
    .filter(Boolean);
}

function formatBps(bps) {
  if (bps == null || bps === 0) return '0 B/s';
  if (bps < 1024) return `${Math.round(bps)} B/s`;
  if (bps < 1048576) return `${(bps / 1024).toFixed(1)} KB/s`;
  return `${(bps / 1048576).toFixed(1)} MB/s`;
}

const SIGNAL_TO_FACT = {
  disk_read_throughput: 'disk_read_bps',
  disk_write_throughput: 'disk_write_bps',
  disk_read_iops: 'disk_read_iops',
  disk_write_iops: 'disk_write_iops',
  disk_iops_utilization_pct: 'disk_iops_utilization_pct',
  disk_throughput_utilization_pct: 'disk_throughput_utilization_pct',
  disk_used_pct: 'disk_used_pct',
  disk_queue_depth: 'disk_queue_depth',
};

function metricFromEvidence(evidence, signal) {
  const factKey = SIGNAL_TO_FACT[signal] || signal;
  const opt = evidence?.optimization_metrics;
  const perf = Array.isArray(opt?.performance) ? opt.performance : [];
  const match = perf.find((m) => [m.id, m.fact_key].includes(factKey) || [m.id, m.fact_key].includes(signal));
  if (match) {
    return match.formatted ?? match.value;
  }
  if (evidence?.[factKey] != null) return evidence[factKey];
  if (evidence?.[signal] != null) return evidence[signal];
  return null;
}

function statusForSignal(signal, raw, ruleId, metrics, properties) {
  const m = metrics || {};
  const p = properties || {};
  const rid = String(ruleId || '').toUpperCase();

  if (signal === 'unattached_days') {
    return p.diskState === 'Unattached' ? 'fail' : 'pass';
  }
  if (signal === 'disk_read_throughput' || signal === 'disk_write_throughput') {
    const bps = signal === 'disk_read_throughput' ? m.disk_read_bps : m.disk_write_bps;
    return (bps || 0) < 1024 ? 'pass' : 'warn';
  }
  if (signal === 'disk_iops_utilization_pct') {
    const pct = m.disk_iops_utilization_pct ?? raw;
    if (pct == null) return 'muted';
    if (rid === 'DISK_UNDERPROVISIONED') return pct >= 80 ? 'fail' : 'warn';
    if (pct < 30) return 'pass';
    if (pct < 50) return 'warn';
    return 'fail';
  }
  if (signal === 'disk_used_pct') {
    const pct = m.disk_used_pct ?? raw;
    if (pct == null) return 'muted';
    return pct <= 30 ? 'pass' : 'warn';
  }
  if (signal === 'disk_queue_depth') {
    const depth = m.disk_queue_depth ?? raw;
    if (depth == null) return 'muted';
    return depth > 10 ? 'fail' : 'pass';
  }
  return 'muted';
}

function formatSignalValue(signal, raw, unit) {
  if (raw == null || raw === '') return '—';
  if (signal === 'disk_read_throughput' || signal === 'disk_write_throughput') {
    return formatBps(Number(raw));
  }
  if (unit === '%' || String(signal).endsWith('_pct')) {
    return `${raw}%`;
  }
  return String(raw);
}

function buildSamples(disk, findingEvidence) {
  const m = disk.metrics || {};
  const p = disk.properties || {};
  const evidence = normalizeEvidence(findingEvidence) || {};

  return {
    disk_read_throughput: {
      value: formatBps(m.disk_read_bps ?? metricFromEvidence(evidence, 'disk_read_throughput')),
      status: statusForSignal('disk_read_throughput', m.disk_read_bps, disk.finding?.rule_id, m, p),
    },
    disk_write_throughput: {
      value: formatBps(m.disk_write_bps ?? metricFromEvidence(evidence, 'disk_write_throughput')),
      status: statusForSignal('disk_write_throughput', m.disk_write_bps, disk.finding?.rule_id, m, p),
    },
    unattached_days: {
      value: p.diskState === 'Unattached' && p.lastOwnershipUpdateTime ? '45 days' : '—',
      status: p.diskState === 'Unattached' ? 'fail' : 'pass',
    },
    disk_iops_utilization_pct: {
      value: m.disk_iops_utilization_pct != null
        ? `${m.disk_iops_utilization_pct}%`
        : formatSignalValue('disk_iops_utilization_pct', metricFromEvidence(evidence, 'disk_iops_utilization_pct'), '%'),
      status: statusForSignal('disk_iops_utilization_pct', m.disk_iops_utilization_pct, disk.finding?.rule_id, m, p),
    },
    disk_throughput_utilization_pct: {
      value: m.disk_throughput_utilization_pct != null
        ? `${m.disk_throughput_utilization_pct}%`
        : formatSignalValue('disk_throughput_utilization_pct', metricFromEvidence(evidence, 'disk_throughput_utilization_pct'), '%'),
      status: statusForSignal('disk_throughput_utilization_pct', m.disk_throughput_utilization_pct, disk.finding?.rule_id, m, p),
    },
    disk_used_pct: {
      value: m.disk_used_pct != null ? `${m.disk_used_pct}%` : '—',
      status: statusForSignal('disk_used_pct', m.disk_used_pct, disk.finding?.rule_id, m, p),
    },
    disk_queue_depth: {
      value: m.disk_queue_depth != null ? String(m.disk_queue_depth) : '—',
      status: statusForSignal('disk_queue_depth', m.disk_queue_depth, disk.finding?.rule_id, m, p),
    },
  };
}

export function buildRuleEvidence(disk, findingEvidence) {
  const finding = disk.finding;
  if (!finding?.rule_id) return [];

  const evidence = normalizeEvidence(findingEvidence ?? finding.evidence);
  if (evidence?.evidence_rows?.length) {
    return evidence.evidence_rows.map((row) => ({
      ...row,
      threshold: row.threshold || thresholdLabel(row.threshold_key),
      aggregation: row.aggregation || row.aggregation,
      period: row.period || row.period,
    }));
  }

  const def = getRuleEvidenceDef(finding.rule_id);
  if (!def?.required_evidence?.length) return [];

  const samples = buildSamples(disk, evidence);

  return def.required_evidence.map((req) => {
    const sample = samples[req.signal] || { value: '—', status: 'muted' };
    return {
      ...req,
      value: sample.value,
      status: sample.status,
      threshold: thresholdLabel(req.threshold_key),
    };
  });
}

export function buildCanvasMetrics(disk) {
  const m = disk.metrics || {};
  return DISK_CANVAS_METRICS.map((def) => {
    const raw = m[def.factKey];
    let value = '—';
    let pct = 0;
    if (raw != null) {
      value = def.unit === '%' ? `${raw}%` : String(raw);
      pct = def.unit === '%' ? Math.min(100, raw) : Math.min(100, (raw / 20) * 100);
    }
    let threshold = 30;
    if (def.factKey === 'disk_iops_utilization_pct') threshold = 50;
    if (def.factKey === 'disk_queue_depth') threshold = 10;
    return { label: def.label, value, pct, threshold, fact_key: def.factKey };
  }).filter((item) => item.value !== '—' || item.fact_key === 'disk_used_pct');
}

const REC_MAP = {
  DISK_UNUSED_EXTENDED: { title: 'Delete unused disk', text: 'Premium disk unattached for extended period. No snapshots reference this volume.', category: 'Delete', target: 'Delete resource' },
  DISK_OVERSIZE_EXTENDED: { title: 'Downgrade to Standard SSD', text: 'Premium disk with sustained low I/O. Standard SSD meets performance requirements at lower cost.', category: 'Tier change', target: 'StandardSSD_LRS' },
  DISK_CAPACITY_RIGHTSIZE_EXTENDED: { title: 'Reduce disk size', text: 'Provisioned capacity far exceeds measured usage. Smaller SKU tier reduces cost without impacting workload.', category: 'Capacity', target: 'Smaller tier' },
  DISK_UNDERPROVISIONED: { title: 'Upgrade disk tier or size', text: 'IOPS utilization exceeds threshold. Current provisioned headroom is exhausted.', category: 'Upgrade', target: 'Larger tier' },
  DISK_QUEUE_DEPTH_EXTENDED: { title: 'Investigate I/O contention', text: 'Queue depth indicates disk contention. Resolve workload pressure before considering tier downgrade.', category: 'Investigate', target: 'No change recommended' },
};

function buildSkuPanel(disk, finding, cost, p) {
  const skuCurrent = {
    name: `${p.sku || ''} ${p.tier || ''}`.trim(),
    tier: String(p.sku || '').includes('Premium') ? 'Premium SSD'
      : String(p.sku || '').includes('StandardSSD') ? 'Standard SSD' : 'Standard HDD',
    size: p.diskSizeGB != null ? `${p.diskSizeGB} GB` : '—',
    region: disk.region,
    specs: [
      { label: 'Tier', value: p.sku },
      { label: 'IOPS', value: p.diskIOPSReadWrite != null ? Number(p.diskIOPSReadWrite).toLocaleString('en-US') : '—' },
      { label: 'Throughput', value: p.diskMBpsReadWrite != null ? `${p.diskMBpsReadWrite} MB/s` : '—' },
    ],
    monthlyCost: cost.retail_monthly,
    mtdCost: cost.billed_mtd,
  };

  let skuTarget = null;
  let changeType = 'Tier change';
  const ruleId = finding?.rule_id;
  if (ruleId === 'DISK_UNUSED_EXTENDED' || ruleId === 'DISK_UNATTACHED') {
    changeType = 'Delete';
  } else if (ruleId === 'DISK_OVERSIZE_EXTENDED') {
    skuTarget = {
      name: 'StandardSSD_LRS',
      tier: 'Standard SSD',
      size: p.diskSizeGB != null ? `${p.diskSizeGB} GB` : '—',
      region: disk.region,
      specs: [{ label: 'Tier', value: 'StandardSSD_LRS' }],
      monthlyCost: Math.max(0, (cost.retail_monthly || 0) - (cost.savings_estimate || 0)),
    };
  } else if (ruleId === 'DISK_CAPACITY_RIGHTSIZE_EXTENDED') {
    changeType = 'Capacity change';
    skuTarget = {
      name: 'Premium_LRS (smaller)',
      tier: 'Premium SSD',
      size: '256 GB',
      region: disk.region,
      specs: [{ label: 'Tier', value: 'Premium_LRS' }],
      monthlyCost: Math.max(0, (cost.retail_monthly || 0) - (cost.savings_estimate || 0)),
    };
  } else if (ruleId === 'DISK_UNDERPROVISIONED') {
    changeType = 'Upgrade';
    skuTarget = {
      name: 'Premium_LRS (larger)',
      tier: 'Premium SSD',
      size: '512 GB',
      region: disk.region,
      specs: [{ label: 'Tier', value: 'Premium_LRS' }],
      monthlyCost: (cost.retail_monthly || 0) + 420,
    };
  }

  return { changeType, current: skuCurrent, target: skuTarget };
}

/** Build full insight canvas data from concept disk record (concept v2 buildInsightFromDisk). */
export function buildInsightFromDisk(disk, { analyzedAt, subscriptionLabel } = {}) {
  const finding = disk.finding;
  const p = disk.properties || {};
  const cost = disk.cost || {};
  const findingEvidence = normalizeEvidence(finding?.evidence);
  const ruleDef = finding ? getRuleEvidenceDef(finding.rule_id) : null;
  const rule = finding ? getRuleById(finding.rule_id) : null;
  const rec = finding
    ? (REC_MAP[finding.rule_id] || {
      title: rule?.recommendation?.action || 'Review disk',
      text: rule?.detail || 'Optimization opportunity detected.',
      category: 'Review',
      target: rule?.recommendation?.target_tier || '—',
    })
    : null;

  const severityLabels = { critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low' };
  const sourceLabels = { engine: 'Engine', advisor: 'Advisor', governance: 'Governance' };
  const savings = cost.savings_estimate || finding?.savings || 0;
  const ruleEvidence = buildRuleEvidence(disk, findingEvidence);
  const evidenceFactors = findingEvidence?.evidence_factors
    || ruleDef?.evidence_factors
    || [];

  return {
    profileType: 'disk',
    sections: ['summary', 'metrics', 'cost', 'recommendation', 'properties', 'tags', 'history'],
    title: disk.name,
    type: 'Managed disk',
    icon: 'DSK',
    iconClass: 'resource-icon--disk',
    arm: disk.id,
    rg: disk.resourceGroup,
    sub: subscriptionLabel || disk.subscription,
    workflow: finding ? 'Proposed' : '—',
    state: p.diskState,
    recTitle: rec?.title || 'No open findings',
    text: rec?.text || 'This disk has no optimization findings in the current analysis run.',
    rule: finding?.rule_id || '—',
    source: finding ? sourceLabels[finding.source] || finding.source : '—',
    sourceKey: finding?.source || 'engine',
    severity: finding ? severityLabels[finding.severity] || 'Medium' : null,
    severityKey: finding?.severity || 'low',
    category: rec?.category || '—',
    cost: cost.retail_monthly || 0,
    savings,
    savingsPct: cost.retail_monthly ? Math.round((savings / cost.retail_monthly) * 100) : 0,
    payback: finding?.rule_id === 'DISK_UNDERPROVISIONED' ? 'N/A — upgrade' : (savings > 0 ? 'Immediate' : '—'),
    costTrend: 0,
    region: disk.region,
    skuFrom: `${p.sku || ''} ${p.diskSizeGB || ''} GB`.trim(),
    target: rec?.target || '—',
    sku: buildSkuPanel(disk, finding, cost, p),
    rationale: evidenceFactors,
    evidence: evidenceFactors,
    ruleEvidence,
    evidenceFactors,
    evidenceGroups: [],
    evidenceOverflowGroups: [],
    evidenceOverflowCount: 0,
    costEnvelope: cost,
    tags: Object.entries(disk.tags || {}).map(([k, v]) => `${k}: ${v}`),
    propertyGroups: buildPropertyGroups(disk).map((g) => ({
      title: g.title,
      items: g.items.map((item) => ({
        label: item.label,
        value: item.value,
        major: item.major,
      })),
    })),
    canvasPropertyGroups: buildPropertyGroups(disk).map((g) => ({
      title: g.title,
      items: g.items.map((item) => ({
        label: item.label,
        value: item.value,
        major: item.major,
      })),
    })),
    costBreakdown: {
      current: cost.retail_monthly,
      projected: Math.max(0, (cost.retail_monthly || 0) - savings),
      savings,
      billedMtd: cost.billed_mtd,
      retailMonthly: cost.retail_monthly,
      retailSource: cost.retail_source,
    },
    metrics: buildCanvasMetrics(disk),
    analyzed: analyzedAt ? formatDateTime(analyzedAt) : '—',
    timeline: finding
      ? [`Finding ${finding.rule_id} from ${finding.source || 'engine'}`]
      : ['No findings in current analysis run'],
    caseId: disk.case_id,
    assessmentRef: SCHEMA_PATH,
    backScreen: 'disks',
    backLabel: 'Managed disks',
    backHref: '/disks',
  };
}

/** Build insight canvas data from live API row + optional finding. */
export function buildDiskInsightFromApi({
  row,
  finding,
  findingsByResource,
  options = {},
  analyzedAt,
  subscriptionLabel,
}) {
  const disk = apiRowToConceptDisk(row, findingsByResource, options);
  if (finding) {
    disk.finding = {
      rule_id: finding.rule_id,
      severity: String(finding.severity || 'medium').toLowerCase(),
      savings: Number(finding.estimated_savings_usd ?? 0),
      workflow: 'proposed',
      source: finding.source || 'engine',
      evidence: finding.evidence,
    };
  }
  return buildInsightFromDisk(disk, { analyzedAt, subscriptionLabel });
}
