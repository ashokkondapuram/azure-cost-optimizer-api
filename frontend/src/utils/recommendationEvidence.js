/** Human-readable evidence rows for recommendations — no config dumps or raw JSON. */

import { buildRuleEvidence } from '../disks/diskInsight';
import { buildEvidenceRows } from './insightCanvasUtils';
import { normalizeEvidence } from './evidenceUtils';
import { toDisplayText } from './formatDisplay';

const INTERNAL_EVIDENCE_KEYS = new Set([
  'assessment_file',
  'required_evidence',
  'exclude_inventory_facts',
  '_evidence_meta',
  'rule_thresholds',
  'data_quality',
  'rule_engine',
  'ai_insight',
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
]);

function isDiskRuleId(ruleId = '') {
  return String(ruleId || '').toUpperCase().startsWith('DISK_');
}

function rowsFromEvidenceRows(evidence) {
  const rows = Array.isArray(evidence?.evidence_rows) ? evidence.evidence_rows : [];
  return rows
    .filter((row) => row?.label && row?.value && row.value !== '—')
    .map((row) => ({
      label: toDisplayText(row.label),
      value: toDisplayText(row.value),
      threshold: row.threshold ? toDisplayText(row.threshold) : null,
      status: row.status || 'muted',
      pillar: row.pillar || 'performance',
    }));
}

function rowsFromEvidenceGroups(groups = []) {
  const rows = [];
  for (const group of groups) {
    for (const row of group.rows || []) {
      if (!row?.label || !row?.value || row.value === '—') continue;
      rows.push({
        label: toDisplayText(row.label),
        value: toDisplayText(row.value),
        threshold: row.hint ? String(row.hint).replace(/^Threshold:\s*/i, '') : null,
        status: row.major ? 'fail' : 'muted',
        pillar: 'performance',
      });
    }
  }
  return rows;
}

function rowsFromDiskRule(finding, context = {}) {
  const evidence = normalizeEvidence(finding?.evidence);
  const metrics = {
    ...(context.row?.metrics || context.row?._metrics || {}),
    ...(context.metrics || {}),
  };
  const properties = context.row?.properties || context.properties || {};
  const disk = {
    finding: {
      rule_id: finding?.rule_id,
      evidence,
    },
    metrics,
    properties,
  };
  const built = buildRuleEvidence(disk, evidence);
  return built.map((row) => ({
    label: toDisplayText(row.label),
    value: toDisplayText(row.value),
    threshold: row.threshold ? toDisplayText(row.threshold) : null,
    status: row.status || 'muted',
    pillar: row.pillar || 'performance',
  }));
}

/** Build display-only evidence rows for one recommendation. */
export function buildRecommendationEvidenceRows(finding, context = {}) {
  if (!finding) return [];

  const evidence = normalizeEvidence(finding.evidence);
  const structured = rowsFromEvidenceRows(evidence);
  if (structured.length) return structured;

  if (isDiskRuleId(finding.rule_id)) {
    const diskRows = rowsFromDiskRule(finding, context);
    if (diskRows.length) return diskRows;
  }

  const { groups, overflowGroups } = buildEvidenceRows(finding);
  const grouped = rowsFromEvidenceGroups([...(groups || []), ...(overflowGroups || [])]);
  return grouped.filter((row) => {
    const label = String(row.label || '').toLowerCase();
    return !INTERNAL_EVIDENCE_KEYS.has(label)
      && !label.includes('assessment file')
      && !label.includes('rule_threshold');
  });
}

export function recommendationDisplayTitle(finding) {
  const name = toDisplayText(finding?.rule_name);
  if (name && name !== '—') return name;
  const rec = toDisplayText(finding?.recommendation);
  if (rec && rec !== '—') return rec;
  return toDisplayText(finding?.rule_id) || 'Recommendation';
}

export function buildRecommendationsPanelModel(findings = [], context = {}) {
  return (findings || [])
    .filter(Boolean)
    .map((finding) => ({
      id: finding.id || finding.rule_id,
      title: recommendationDisplayTitle(finding),
      savings: Number(finding.estimated_savings_usd || 0),
      severity: finding.severity,
      ruleId: finding.rule_id,
      recommendation: toDisplayText(finding.recommendation),
      evidenceRows: buildRecommendationEvidenceRows(finding, context),
      factors: Array.isArray(finding.evidence?.evidence_factors)
        ? finding.evidence.evidence_factors
        : [],
    }));
}
