/** Row display helpers for Action centre — one fact per column, no repeated copy. */

import { topFindingHeadline } from './findingFilters';
import { classifyFindingSourceKey } from './findingsSummaryUtils';
import { findingRecommendedRegion } from './pillarEvidence';
import { resourceGroupLabelFromRow, formatCategoryLabel } from './taxonomy';

const SOURCE_BADGE_SHORT = {
  cost_performance: 'Cost',
  reliability_security: 'Advisor',
  governance: 'Governance',
};

function escapeRegex(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Remove region phrases already shown on the secondary line. */
export function stripRegionFromHeadline(headline, region) {
  if (!headline || !region) return headline || '';
  const regionEsc = escapeRegex(region);
  let text = String(headline);
  const patterns = [
    new RegExp(`\\s*→\\s*${regionEsc}\\b`, 'gi'),
    new RegExp(`\\s*to\\s+${regionEsc}\\b`, 'gi'),
    new RegExp(`\\s*in\\s+${regionEsc}\\b`, 'gi'),
    new RegExp(`\\(${regionEsc}\\)`, 'gi'),
    new RegExp(`\\b${regionEsc}\\b`, 'gi'),
  ];
  for (const pattern of patterns) {
    text = text.replace(pattern, ' ').replace(/\s{2,}/g, ' ').trim();
  }
  return text || headline;
}

export function sourceBadgeLabel(finding, sourceLabels = {}) {
  if (!finding) return null;
  const key = classifyFindingSourceKey(finding);
  if (SOURCE_BADGE_SHORT[key]) return SOURCE_BADGE_SHORT[key];
  const fromApi = sourceLabels[key];
  if (fromApi) {
    if (fromApi.toLowerCase().includes('cost')) return 'Cost';
    if (fromApi.toLowerCase().includes('advisor') || fromApi.toLowerCase().includes('reliability')) {
      return 'Advisor';
    }
    if (fromApi.toLowerCase().includes('govern')) return 'Governance';
    return fromApi.split(/[&/]/)[0].trim();
  }
  return SOURCE_BADGE_SHORT[key] || null;
}

export function categoryLabelForRec(rec) {
  const category = rec?.topFinding?.category_label
    || rec?.topFinding?.category
    || rec?.findings?.[0]?.category_label
    || rec?.findings?.[0]?.category;
  return category ? formatCategoryLabel(category) : '—';
}

export function resourceMetaLine(row) {
  return resourceGroupLabelFromRow(row) || '—';
}

/**
 * Build non-overlapping copy for the recommendation column.
 * Headline = issue one-liner; secondary = region and/or extra issue count only.
 */
export function buildActionCentreRowDisplay(rec, sourceLabels = {}) {
  const finding = rec?.topFinding ?? null;
  const findingCount = Number(rec?.findingCount ?? 0);
  const extraFindings = finding && findingCount > 1 ? findingCount - 1 : 0;

  if (!finding) {
    return {
      finding: null,
      headline: null,
      secondaryLine: null,
      sourceBadge: null,
      sourceKey: null,
      severity: null,
    };
  }

  const region = findingRecommendedRegion(finding);
  const rawHeadline = topFindingHeadline(finding);
  const headline = region ? stripRegionFromHeadline(rawHeadline, region) : rawHeadline;
  const secondaryParts = [];
  if (region) secondaryParts.push(`→ ${region}`);
  if (extraFindings > 0) secondaryParts.push(`+${extraFindings} more`);

  return {
    finding,
    headline,
    secondaryLine: secondaryParts.length ? secondaryParts.join(' · ') : null,
    sourceBadge: sourceBadgeLabel(finding, sourceLabels),
    sourceKey: classifyFindingSourceKey(finding),
    severity: finding.severity || null,
  };
}
