/** Shared category/severity ordering for findings and resource rows. */

import { serviceDisplayNameForRow } from '../config/assetIcons';
import { toDisplayText } from './formatDisplay';

export const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

export const SEVERITY_RANK = Object.fromEntries(
  SEVERITY_ORDER.map((key, index) => [key, index]),
);

export const SEVERITY_LABELS = {
  CRITICAL: 'Critical',
  HIGH: 'High',
  MEDIUM: 'Medium',
  LOW: 'Low',
  INFO: 'Info',
};

export const CATEGORY_ORDER = [
  'COMPUTE',
  'KUBERNETES',
  'STORAGE',
  'NETWORK',
  'DATABASE',
  'SECURITY',
  'COST',
  'GOVERNANCE',
  'RELIABILITY',
  'OTHER',
];

export const CATEGORY_RANK = Object.fromEntries(
  CATEGORY_ORDER.map((key, index) => [key, index]),
);

export const CATEGORY_LABELS = {
  COMPUTE: 'Compute',
  KUBERNETES: 'Kubernetes',
  STORAGE: 'Storage',
  NETWORK: 'Network',
  DATABASE: 'Database',
  SECURITY: 'Security',
  COST: 'Cost',
  GOVERNANCE: 'Governance',
  RELIABILITY: 'Reliability',
  OTHER: 'Other',
};

export function normalizeSeverity(severity) {
  const raw = toDisplayText(severity || 'INFO');
  const key = String(raw === '—' ? 'INFO' : raw).toUpperCase();
  return SEVERITY_RANK[key] !== undefined ? key : 'INFO';
}

export function normalizeCategory(category) {
  const raw = toDisplayText(category || 'OTHER');
  const key = String(raw === '—' ? 'OTHER' : raw).toUpperCase();
  return CATEGORY_RANK[key] !== undefined ? key : 'OTHER';
}

export function formatCategoryLabel(category) {
  const key = normalizeCategory(category);
  if (CATEGORY_LABELS[key]) return CATEGORY_LABELS[key];
  const lower = key.toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

export function formatSeverityLabel(severity) {
  const key = normalizeSeverity(severity);
  return SEVERITY_LABELS[key] || key;
}

export function compareSeverity(a, b) {
  return (SEVERITY_RANK[normalizeSeverity(a)] ?? 9)
    - (SEVERITY_RANK[normalizeSeverity(b)] ?? 9);
}

export function compareCategory(a, b) {
  return (CATEGORY_RANK[normalizeCategory(a)] ?? 99)
    - (CATEGORY_RANK[normalizeCategory(b)] ?? 99);
}

export function sortFindingsByPriority(findings = []) {
  return [...findings].sort((a, b) => {
    const severityDelta = compareSeverity(a.severity, b.severity);
    if (severityDelta !== 0) return severityDelta;
    const savingsDelta = (b.estimated_savings_usd || 0) - (a.estimated_savings_usd || 0);
    if (savingsDelta !== 0) return savingsDelta;
    return String(b.detected_at || '').localeCompare(String(a.detected_at || ''));
  });
}

export function compareResourceRowsByPriority(a, b) {
  const sevA = a?.rec?.topFinding?.severity;
  const sevB = b?.rec?.topFinding?.severity;
  const severityDelta = compareSeverity(sevA, sevB);
  if (severityDelta !== 0) return severityDelta;
  const savingsDelta = (b?.rec?.savings || 0) - (a?.rec?.savings || 0);
  if (savingsDelta !== 0) return savingsDelta;
  const issuesDelta = (b?.rec?.findingCount || 0) - (a?.rec?.findingCount || 0);
  if (issuesDelta !== 0) return issuesDelta;
  return String(a?.row?.name || '').localeCompare(String(b?.row?.name || ''));
}

export function groupRowsByService(rows = []) {
  const map = new Map();
  for (const entry of rows) {
    const service = serviceDisplayNameForRow(entry.row) || 'Other';
    if (!map.has(service)) {
      map.set(service, {
        key: service,
        label: service,
        rows: [],
        savings: 0,
      });
    }
    const group = map.get(service);
    group.rows.push(entry);
    group.savings += entry.rec?.savings || 0;
  }
  return [...map.values()].sort((a, b) => {
    if (b.savings !== a.savings) return b.savings - a.savings;
    if (b.rows.length !== a.rows.length) return b.rows.length - a.rows.length;
    return a.label.localeCompare(b.label);
  });
}

export function resourceGroupLabelFromRow(row) {
  return row?.resourceGroup
    || row?.resource_group
    || (String(row?.id || row?.resource_id || '').split('/')[4] || '')
    || '—';
}

export function groupRowsByResourceGroup(rows = []) {
  const map = new Map();
  for (const entry of rows) {
    const rg = resourceGroupLabelFromRow(entry.row);
    if (!map.has(rg)) {
      map.set(rg, {
        key: rg,
        label: rg,
        rows: [],
        savings: 0,
      });
    }
    const group = map.get(rg);
    group.rows.push(entry);
    group.savings += entry.rec?.savings || 0;
  }
  return [...map.values()].sort((a, b) => {
    if (b.savings !== a.savings) return b.savings - a.savings;
    if (b.rows.length !== a.rows.length) return b.rows.length - a.rows.length;
    return a.label.localeCompare(b.label);
  });
}

export const WIZ_RESOURCE_GROUP_BY_OPTIONS = [
  { value: '', label: 'No grouping' },
  { value: 'service', label: 'Service' },
  { value: 'resource_group', label: 'Resource group' },
];

/** Group enriched resource rows for wiz table views. Returns null when flat. */
export function groupResourceRows(rows = [], groupBy = '') {
  if (groupBy === 'service') return groupRowsByService(rows);
  if (groupBy === 'resource_group') return groupRowsByResourceGroup(rows);
  return null;
}

export function orderedBreakdownFromSummary(summary, field = 'by_category_ordered') {
  const ordered = summary?.[field];
  if (Array.isArray(ordered) && ordered.length) return ordered;
  const raw = field === 'by_severity_ordered' ? summary?.by_severity : summary?.by_category;
  if (!raw || typeof raw !== 'object') return [];
  const kind = field === 'by_severity_ordered' ? 'severity' : 'category';
  const order = kind === 'severity' ? SEVERITY_ORDER : CATEGORY_ORDER;
  const labels = kind === 'severity' ? SEVERITY_LABELS : CATEGORY_LABELS;
  return order
    .filter((key) => raw[key] > 0)
    .map((key) => ({
      key,
      label: labels[key] || key,
      count: raw[key],
      estimated_savings_usd: 0,
    }));
}
