/** Normalize findings summary payloads from GET /optimize/findings/summary. */

const SOURCE_KEYS = ['cost_performance', 'reliability_security', 'governance'];

export function openFindingsCount(summary) {
  if (!summary) return 0;
  return summary.action_centre_open_findings
    ?? summary.open_findings
    ?? summary.open_count
    ?? summary.total_open
    ?? 0;
}

export function openFindingsAllCount(summary) {
  if (!summary) return 0;
  return summary.open_findings_all ?? openFindingsCount(summary);
}

export function resourcesWithFindings(summary) {
  return Number(summary?.resources_with_findings ?? 0);
}

export function sourceBreakdown(summary) {
  return summary?.by_source || {};
}

export function sourceBreakdownOrdered(summary) {
  if (summary?.by_source_ordered?.length) {
    return summary.by_source_ordered;
  }
  const labels = summary?.source_labels || {};
  return SOURCE_KEYS
    .map((key) => ({
      key,
      label: labels[key] || key,
      count: Number(summary?.by_source?.[key] ?? 0),
    }))
    .filter((item) => item.count > 0);
}

export function excludedFindingsSummary(summary) {
  const excluded = summary?.excluded || {};
  const metricGaps = Number(excluded.metric_gaps ?? 0);
  const costExportOnly = Number(excluded.cost_export_only ?? 0);
  const total = Number(excluded.total ?? metricGaps + costExportOnly);
  return { metric_gaps: metricGaps, cost_export_only: costExportOnly, total };
}

export function classifyFindingSourceKey(finding) {
  const ruleId = String(finding?.rule_id || '').toLowerCase();
  const evidence = finding?.evidence || {};
  const engine = String(evidence.engine || evidence.rule_source || '').toLowerCase();

  if (ruleId.startsWith('advisor_') || engine === 'azure_advisor') {
    return 'reliability_security';
  }
  const category = String(finding?.category || '').toUpperCase();
  if (category === 'RELIABILITY' || category === 'SECURITY') {
    return 'reliability_security';
  }
  if (category === 'GOVERNANCE' || ruleId.startsWith('governance_')) {
    return 'governance';
  }
  return 'cost_performance';
}

export function sourceBreakdownSubline(summary) {
  return sourceBreakdownOrdered(summary)
    .filter((item) => item.count > 0)
    .map((item) => `${item.count.toLocaleString()} ${item.label.toLowerCase()}`)
    .join(' · ');
}

export function totalEstimatedSavings(summary) {
  if (!summary) return 0;
  return summary.unified_savings?.unified_estimated_monthly_savings
    ?? summary.engine_unified_savings_usd
    ?? summary.total_estimated_savings_usd
    ?? summary.estimated_savings_usd
    ?? 0;
}

export function severityBreakdown(summary) {
  return summary?.by_severity || summary?.severity || {};
}

export function categoryBreakdown(summary) {
  return summary?.by_category || {};
}

export function normalizeFindingsSummary(summary) {
  if (!summary) return null;
  const open = openFindingsCount(summary);
  return {
    ...summary,
    open_findings: open,
    open_count: open,
    total_open: open,
    total_estimated_savings_usd: totalEstimatedSavings(summary),
    by_severity: severityBreakdown(summary),
    by_category: categoryBreakdown(summary),
    by_source_ordered: sourceBreakdownOrdered(summary),
  };
}
