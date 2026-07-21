/** Grouping and summary helpers for the recommendations page. */

import { sumUnifiedSavingsForFindings } from './unifiedSavings';
import {
  SEVERITY_ORDER,
  SEVERITY_LABELS,
  formatCategoryLabel,
  sortFindingsByPriority,
} from './taxonomy';

export {
  SEVERITY_ORDER,
  SEVERITY_LABELS,
  formatCategoryLabel,
  sortFindingsByPriority,
} from './taxonomy';

export function groupFindingsBySeverity(findings) {
  const buckets = {};
  for (const finding of findings || []) {
    const severity = (finding.severity || 'INFO').toUpperCase();
    if (!buckets[severity]) buckets[severity] = [];
    buckets[severity].push(finding);
  }
  return SEVERITY_ORDER
    .filter((severity) => buckets[severity]?.length)
    .map((severity) => {
      const items = sortFindingsByPriority(buckets[severity]);
      return {
        severity,
        label: SEVERITY_LABELS[severity] || severity,
        findings: items,
        savings: sumUnifiedSavingsForFindings(items),
      };
    });
}

export function summarizeBySeverity(findings) {
  const groups = groupFindingsBySeverity(findings);
  const totalCount = findings?.length || 0;
  const totalSavings = sumUnifiedSavingsForFindings(findings);
  return { groups, totalCount, totalSavings };
}

export function findingAffectedLabel(finding) {
  if (finding?.resource_name) {
    return `1 resource · ${finding.resource_name}`;
  }
  if (finding?.resource_group) {
    return finding.resource_group;
  }
  return 'Subscription';
}
