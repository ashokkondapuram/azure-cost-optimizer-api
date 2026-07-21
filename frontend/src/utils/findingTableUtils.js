/** Optimization engine finding helpers for compact table icon chips. */

import { formatCategoryLabel } from './recommendationGrouping';

const SEVERITY_RANK = {
  CRITICAL: 0,
  HIGH: 1,
  MEDIUM: 2,
  LOW: 3,
  INFO: 4,
};

const SEVERITY_TONES = {
  CRITICAL: 'high',
  HIGH: 'high',
  MEDIUM: 'medium',
  LOW: 'low',
  INFO: 'muted',
};

/** Categories shown as icon-only chips from the recommendation engine. */
export const FINDING_TABLE_CATEGORIES = [
  'COST',
  'RELIABILITY',
  'SECURITY',
  'COMPUTE',
  'KUBERNETES',
  'STORAGE',
  'NETWORK',
  'DATABASE',
  'GOVERNANCE',
];

export function findingSeverityTone(severity) {
  const key = String(severity || '').toUpperCase();
  return SEVERITY_TONES[key] || 'muted';
}

export function findingCategoryLabel(category) {
  return formatCategoryLabel(category);
}

/** One finding per category, highest severity first. */
export function findingCategoriesForTable(findings = []) {
  if (!findings?.length) return [];
  const byCategory = new Map();

  for (const finding of findings) {
    const category = String(finding.category || 'OTHER').toUpperCase();
    if (!FINDING_TABLE_CATEGORIES.includes(category)) continue;
    const existing = byCategory.get(category);
    if (!existing) {
      byCategory.set(category, finding);
      continue;
    }
    const ia = SEVERITY_RANK[String(existing.severity || '').toUpperCase()] ?? 5;
    const ib = SEVERITY_RANK[String(finding.severity || '').toUpperCase()] ?? 5;
    if (ib < ia) {
      byCategory.set(category, finding);
      continue;
    }
    if (ib === ia && (finding.estimated_savings_usd || 0) > (existing.estimated_savings_usd || 0)) {
      byCategory.set(category, finding);
    }
  }

  return FINDING_TABLE_CATEGORIES
    .filter((category) => byCategory.has(category))
    .map((category) => byCategory.get(category));
}
