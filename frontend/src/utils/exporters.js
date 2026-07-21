import { downloadCsv, toCsv } from './csvExport';
import { resourceTotalCost } from './costCurrency';
import { toDisplayText, formatPowerState } from './formatDisplay';
import { resourceGroupOf } from './filterUtils';
import { resolveResourceSku } from './resourceSkuUtils';

function stampFilename(prefix) {
  return `${prefix}-${new Date().toISOString().slice(0, 10)}.csv`;
}

function resolveRowState(row) {
  const raw = row.state
    || row.properties?.diskState
    || row.properties?.powerState
    || row.properties?.provisioningState;
  if (raw == null || raw === '') return '';
  return formatPowerState(raw);
}

/**
 * Export visible resource rows as CSV.
 */
export function exportAllResourcesCSV(resources, filename) {
  const rows = (resources || []).map((row) => ({
    Name: toDisplayText(row.name || row.resource_name),
    'Resource group': resourceGroupOf(row),
    Location: row.location || '',
    SKU: toDisplayText(resolveResourceSku(row)),
    State: resolveRowState(row),
    'Monthly cost': resourceTotalCost(row),
    'Resource ID': row.id || row.resource_id || '',
  }));
  downloadCsv(filename || stampFilename('resources'), toCsv(rows));
}

/**
 * Export recommendation / finding rows as CSV.
 */
export function exportRecommendationsCSV(findings, filename) {
  const rows = (findings || []).map((finding) => ({
    Rule: finding.rule_name || '',
    Severity: finding.severity || '',
    Category: finding.category || '',
    Status: finding.status || '',
    Resource: finding.resource_name || '',
    'Resource group': finding.resource_group || '',
    'Est. savings/mo': finding.estimated_savings_usd ?? '',
    Recommendation: finding.recommendation || '',
  }));
  downloadCsv(filename || stampFilename('recommendations'), toCsv(rows));
}
