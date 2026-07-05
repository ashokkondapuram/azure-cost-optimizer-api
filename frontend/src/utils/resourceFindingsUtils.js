/**
 * Resolve open findings for a resource row for consistent list badges and drawer panels.
 * Prefer live findings from the index; fall back to denormalized analysisSummary only
 * while the index is still loading.
 */

function defaultResourceId(resource) {
  return (resource?.id || resource?.resource_id || '').toLowerCase();
}

function findingsFromCountFallback(resource) {
  const count = Number(resource?.analysisFindingsCount ?? 0);
  if (count <= 0) return [];

  const summary = resource?.analysisSummary;
  if (Array.isArray(summary) && summary.length) {
    return summary.map((item, index) => normalizeSummaryItem(item, index, resource));
  }

  const severity = resource?.analysisTopSeverity || 'MEDIUM';
  return [{
    id: 'analysis-count-0',
    severity,
    estimated_savings_usd: resource?.analysisSavingsUsd ?? 0,
  }];
}

function normalizeSummaryItem(item, index, resource) {
  return {
    id: item.rule_id || item.id || `analysis-summary-${index}`,
    rule_id: item.rule_id,
    rule_name: item.rule_name,
    severity: item.severity || resource?.analysisTopSeverity || 'MEDIUM',
    detail: item.detail || item.recommendation,
    recommendation: item.recommendation,
    estimated_savings_usd: item.estimated_savings_usd ?? 0,
  };
}


export function resolveResourceFindings(resource, indexFindings = [], options = {}) {
  const { indexReady = false } = options;

  if (indexReady) {
    return indexFindings ?? [];
  }

  if (indexFindings?.length) return indexFindings;

  const summary = resource?.analysisSummary;
  if (Array.isArray(summary) && summary.length) {
    return summary.map((item, index) => normalizeSummaryItem(item, index, resource));
  }

  return findingsFromCountFallback(resource);
}

export function resolveResourceSavings(resource, indexFindings = [], savingsFromIndex = 0, options = {}) {
  const resolved = resolveResourceFindings(resource, indexFindings, options);
  if (!resolved.length) return 0;

  if (indexFindings?.length || options.indexReady) {
    return savingsFromIndex > 0
      ? savingsFromIndex
      : resolved.reduce((sum, f) => sum + (f.estimated_savings_usd || 0), 0);
  }

  return resource?.analysisSavingsUsd
    ?? resolved.reduce((sum, f) => sum + (f.estimated_savings_usd || 0), 0);
}

export function resourceHasFindings(resource, indexFindings = [], options = {}) {
  return resolveResourceFindings(resource, indexFindings, options).length > 0;
}

export function countResourcesWithFindings(
  rows,
  byResourceId,
  getResourceId = defaultResourceId,
  options = {},
) {
  return rows.filter((row) => {
    const rid = getResourceId(row);
    return resourceHasFindings(row, byResourceId.get(rid) || [], options);
  }).length;
}

export function countOpenFindings(
  rows,
  byResourceId,
  getResourceId = defaultResourceId,
  options = {},
) {
  return rows.reduce(
    (total, row) => {
      const rid = getResourceId(row);
      return total + resolveResourceFindings(row, byResourceId.get(rid) || [], options).length;
    },
    0,
  );
}

export function sumResolvedSavingsForRows(
  rows,
  byResourceId,
  savingsByResource,
  getResourceId = defaultResourceId,
  options = {},
) {
  return rows.reduce((sum, row) => {
    const rid = getResourceId(row);
    const indexFindings = byResourceId.get(rid) || [];
    return sum + resolveResourceSavings(row, indexFindings, savingsByResource.get(rid) || 0, options);
  }, 0);
}
