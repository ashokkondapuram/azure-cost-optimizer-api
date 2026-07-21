import { resolveUnifiedResourceSavings } from './unifiedSavings';
import { pickPrimaryCosmosFindings } from './cosmosPrimaryFinding';
import { normalizeArmId } from './findingDedupe';

/**
 * Resolve open findings for a resource row for consistent list badges and drawer panels.
 * Prefer live findings from the index; fall back to denormalized analysisSummary only
 * while the index is still loading.
 */

function defaultResourceId(resource) {
  return normalizeArmId(resource?.id || resource?.resource_id || '');
}

function findingsFromSummary(resource) {
  const summary = resource?.analysisSummary;
  if (!Array.isArray(summary) || !summary.length) return null;

  const count = Number(resource?.analysisFindingsCount ?? 0);
  const normalized = summary.map((item, index) => normalizeSummaryItem(item, index, resource));
  if (count > normalized.length) {
    const padded = [...normalized];
    for (let i = normalized.length; i < count; i += 1) {
      padded.push({
        id: `analysis-count-${i}`,
        severity: resource?.analysisTopSeverity || 'MEDIUM',
        estimated_savings_usd: 0,
      });
    }
    return padded;
  }
  return normalized;
}

function findingsFromCountFallback(resource) {
  const count = Number(resource?.analysisFindingsCount ?? 0);
  if (count <= 0) return [];

  const fromSummary = findingsFromSummary(resource);
  if (fromSummary) return fromSummary;

  const severity = resource?.analysisTopSeverity || 'MEDIUM';
  return Array.from({ length: count }, (_, index) => ({
    id: `analysis-count-${index}`,
    severity,
    estimated_savings_usd: 0,
  }));
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


function resolveFindingsFromSources(resource, indexFindings = [], options = {}) {
  const { indexReady = false } = options;
  const summaryFindings = findingsFromSummary(resource) || findingsFromCountFallback(resource);

  if (indexFindings?.length) return indexFindings;
  if (indexReady) return summaryFindings.length ? summaryFindings : [];
  if (summaryFindings.length) return summaryFindings;
  return [];
}

export function resolveResourceFindings(resource, indexFindings = [], options = {}) {
  const { apiPath = '' } = options;
  const result = resolveFindingsFromSources(resource, indexFindings, options);
  return pickPrimaryCosmosFindings(result, resource, apiPath);
}

/** Drawer view — keep every open finding; list UI may still highlight a primary recommendation. */
export function resolveDrawerResourceFindings(resource, indexFindings = [], options = {}) {
  return resolveFindingsFromSources(resource, indexFindings, options);
}

export function resolveResourceSavings(resource, indexFindings = [], savingsFromIndex = 0, options = {}) {
  const resolved = resolveResourceFindings(resource, indexFindings, options);
  if (!resolved.length && !(resource?.analysisSavingsUsd > 0)) return 0;

  const rid = defaultResourceId(resource);
  const savingsMap = options.savingsByResource instanceof Map
    ? options.savingsByResource
    : (savingsFromIndex > 0 ? new Map([[rid, savingsFromIndex]]) : null);

  return resolveUnifiedResourceSavings({
    resourceId: resource?.id || resource?.resource_id,
    findings: indexFindings?.length ? indexFindings : resolved,
    savingsByResource: savingsMap,
    analysisSavingsUsd: resource?.analysisSavingsUsd,
    indexReady: Boolean(options.indexReady || indexFindings?.length),
  });
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
