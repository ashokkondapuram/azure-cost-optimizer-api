/** Grouping and summary helpers for the recommendations page. */

export const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

export const SEVERITY_LABELS = {
  CRITICAL: 'Critical',
  HIGH: 'High',
  MEDIUM: 'Medium',
  LOW: 'Low',
  INFO: 'Info',
};

const CATEGORY_LABELS = {
  COMPUTE: 'Compute',
  KUBERNETES: 'Kubernetes',
  STORAGE: 'Storage',
  NETWORK: 'Network',
  DATABASE: 'Database',
  SECURITY: 'Security',
  COST: 'Cost',
};

export function formatCategoryLabel(category) {
  const key = String(category || 'Other').toUpperCase();
  if (CATEGORY_LABELS[key]) return CATEGORY_LABELS[key];
  const lower = key.toLowerCase();
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

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
      const items = [...buckets[severity]].sort(
        (a, b) => (b.estimated_savings_usd || 0) - (a.estimated_savings_usd || 0),
      );
      return {
        severity,
        label: SEVERITY_LABELS[severity] || severity,
        findings: items,
        savings: items.reduce((sum, f) => sum + (f.estimated_savings_usd || 0), 0),
      };
    });
}

export function summarizeBySeverity(findings) {
  const groups = groupFindingsBySeverity(findings);
  const totalCount = findings?.length || 0;
  const totalSavings = (findings || []).reduce((s, f) => s + (f.estimated_savings_usd || 0), 0);
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
