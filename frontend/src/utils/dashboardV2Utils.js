import { sparklinePoints } from './visualPolish';
import {
  formatCategoryLabel,
  formatSeverityLabel,
  normalizeCategory,
  orderedBreakdownFromSummary,
  SEVERITY_ORDER,
} from './taxonomy';
import {
  openFindingsCount,
  resourcesWithFindings,
  sourceBreakdown,
  totalEstimatedSavings,
  excludedFindingsSummary,
} from './findingsSummaryUtils';

/** Prototype-style currency: "CAD 42,180.00" */
export function formatIsoCurrency(amount, currency = 'CAD', { decimals = 2 } = {}) {
  if (amount == null || Number.isNaN(Number(amount))) return `${currency} —`;
  const value = Number(amount);
  return `${currency} ${value.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

export const PROTOTYPE_SPARKLINE = {
  linePath: 'M0 42 L40 38 L80 44 L120 28 L160 32 L200 18 L240 24 L280 12 L320 16',
  fillPath: 'M0 42 L40 38 L80 44 L120 28 L160 32 L200 18 L240 24 L280 12 L320 16 L320 56 L0 56 Z',
  lastPoint: { x: 320, y: 16 },
};

export const CATEGORY_COLORS = {
  COMPUTE: '#60a5fa',
  STORAGE: '#fbbf24',
  DATABASE: '#f87171',
  KUBERNETES: '#a78bfa',
  NETWORK: '#34d399',
  COST: '#22d3ee',
  SECURITY: '#fb923c',
  GOVERNANCE: '#f97316',
  RELIABILITY: '#a78bfa',
  OTHER: '#94a3b8',
};

export const SOURCE_CHIPS = [
  { id: 'all', label: 'All sources', color: null },
  { id: 'engine', sourceKey: 'cost_performance', label: 'Engine', color: '#0073ff' },
  { id: 'advisor', sourceKey: 'reliability_security', label: 'Advisor', color: '#8b5cf6' },
  { id: 'governance', sourceKey: 'governance', label: 'Governance', color: '#f97316' },
];

export const FALLBACK = {
  openFindings: 47,
  resourcesAffected: 32,
  withSavings: 35,
  excludedGaps: 2,
  proposed: 12,
  approved: 8,
  executed: 24,
  potentialSavings: 8420,
  weeklyAvg: 9840,
  mtdSpend: 42180,
  projectedMonthly: 78400,
  mtdDelta: -1240,
  severity: { CRITICAL: 6, HIGH: 14, MEDIUM: 19, LOW: 8 },
  categories: [
    { key: 'COMPUTE', count: 14 },
    { key: 'STORAGE', count: 11 },
    { key: 'DATABASE', count: 8 },
    { key: 'KUBERNETES', count: 5 },
    { key: 'NETWORK', count: 4 },
    { key: 'COST', count: 3 },
    { key: 'SECURITY', count: 2 },
  ],
  sources: { cost_performance: 26, reliability_security: 14, governance: 7 },
  opportunities: [
    {
      resource_name: 'prod-sql-primary',
      rule_name: 'Right-size SQL Database',
      category: 'DATABASE',
      estimated_savings_usd: 890,
      severity: 'CRITICAL',
    },
    {
      resource_name: 'legacy-vm-batch',
      rule_name: 'Deallocate idle VM',
      category: 'COMPUTE',
      estimated_savings_usd: 720,
      severity: 'HIGH',
    },
    {
      resource_name: 'aks-prod-pool-2',
      rule_name: 'Resize node pool',
      category: 'KUBERNETES',
      estimated_savings_usd: 420,
      severity: 'MEDIUM',
    },
  ],
};

export function buildSparklineGeometry(dailyPoints, width = 320, height = 56, padding = 10) {
  const rows = sparklinePoints(dailyPoints, 9);
  if (rows.length < 2) return null;

  const costs = rows.map((r) => r.cost);
  const min = Math.min(...costs);
  const max = Math.max(...costs);
  const range = max - min || 1;

  const coords = rows.map((row, i) => {
    const x = (i / (rows.length - 1)) * width;
    const y = height - padding - ((row.cost - min) / range) * (height - padding * 2);
    return { x: Math.round(x), y: Math.round(y) };
  });

  const linePath = coords.map((c, i) => `${i === 0 ? 'M' : 'L'}${c.x} ${c.y}`).join(' ');
  const last = coords[coords.length - 1];
  const fillPath = `${linePath} L${width} ${height} L0 ${height} Z`;

  return { linePath, fillPath, lastPoint: last };
}

export function severityRows(summary) {
  const raw = summary?.by_severity || summary?.severity || {};
  const total = SEVERITY_ORDER.reduce((sum, key) => sum + Number(raw[key] || 0), 0) || 1;

  return ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((key) => {
    const count = Number(raw[key] || 0);
    return {
      key,
      label: formatSeverityLabel(key),
      count,
      pct: Math.round((count / total) * 100),
      className: key.toLowerCase(),
    };
  });
}

export function categoryRows(summary) {
  const ordered = orderedBreakdownFromSummary(summary, 'by_category_ordered');
  const rows = ordered.map((row) => ({
    key: normalizeCategory(row.key || row.category),
    label: row.label || formatCategoryLabel(row.key),
    count: Number(row.count || 0),
  }));

  const max = Math.max(...rows.map((r) => r.count), 1);
  return rows
    .filter((r) => r.count > 0)
    .map((r) => ({
      ...r,
      color: CATEGORY_COLORS[r.key] || CATEGORY_COLORS.OTHER,
      widthPct: Math.round((r.count / max) * 100),
    }));
}

export function sourceChipCounts(summary) {
  const bySource = sourceBreakdown(summary);
  return SOURCE_CHIPS.map((chip) => {
    if (chip.id === 'all') {
      return { ...chip, count: null };
    }
    return {
      ...chip,
      count: Number(bySource[chip.sourceKey] || 0),
    };
  });
}

export function findingsLeadText(summary, sourceId = 'all', resourcesAffected) {
  const open = openFindingsCount(summary);
  const resources = resourcesAffected ?? resourcesWithFindings(summary);

  if (sourceId === 'all') {
    return `${open.toLocaleString()} open issues across ${resources.toLocaleString()} resources`;
  }

  const chip = SOURCE_CHIPS.find((c) => c.id === sourceId);
  const bySource = sourceBreakdown(summary);
  const count = Number(bySource[chip?.sourceKey] || 0);
  const label = chip?.label || 'Source';
  return `${count.toLocaleString()} open issues from ${label} across ${resources.toLocaleString()} resources`;
}

export function severityInsight(rows) {
  const criticalHigh = rows.filter((r) => r.key === 'CRITICAL' || r.key === 'HIGH');
  const pct = criticalHigh.reduce((sum, r) => sum + r.pct, 0);
  if (!pct) {
    return 'No critical or high findings in the current summary.';
  }
  return `Critical and high findings account for ${pct}% of open issues and most actionable savings.`;
}

export function categoryInsight(rows) {
  if (!rows.length) {
    return 'No open findings by category yet.';
  }
  const top = rows[0];
  const open = rows.reduce((sum, r) => sum + r.count, 0) || 1;
  const pct = Math.round((top.count / open) * 100);
  return `${top.label} leads with ${top.count} issues — ${pct}% of your open findings.`;
}

export function categoryHoverInsight(row) {
  return `${row.count} open issues in ${row.label} — click to review in action centre.`;
}

export function savingsPctOfMtd(savings, mtd) {
  if (!mtd || mtd <= 0) return null;
  return Math.round((savings / mtd) * 100);
}

/** Coerce GET /dashboard/overview payloads into a stable dashboard shape. */
export function normalizeDashboardOverview(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const cost = raw.cost && typeof raw.cost === 'object' ? raw.cost : {};
  const optimization = raw.optimization && typeof raw.optimization === 'object'
    ? raw.optimization
    : {};
  return {
    ...raw,
    portal: raw.portal || null,
    cost: {
      ...cost,
      summary: cost.summary ?? null,
      daily: cost.daily ?? { points: [] },
    },
    optimization: {
      ...optimization,
      summary: optimization.summary ?? null,
      recommendations: optimization.recommendations ?? { items: [] },
    },
    sync: raw.sync ?? null,
    inventory: raw.inventory ?? null,
  };
}

/** True when the overview has enough structure to render dashboard widgets. */
export function hasDashboardOverviewData(overview) {
  if (!overview || typeof overview !== 'object') return false;
  if (overview.portal) return true;
  if (overview.cost?.summary) return true;
  if (overview.optimization?.summary) return true;
  if (overview.inventory?.counts) return true;
  if (overview.sync?.inventory || overview.sync?.cost || overview.sync?.analysis) return true;
  return Boolean(overview.subscription_id);
}

export function inventoryAffectedPct(resourcesAffected, inventoryTotal) {
  if (!inventoryTotal || inventoryTotal <= 0) return null;
  return Math.round((resourcesAffected / inventoryTotal) * 10) / 10;
}

export function resolveDashboardMetrics({
  summary,
  portal,
  costSummary,
  currency,
  trends,
}) {
  const kpisById = Object.fromEntries((portal?.kpis || []).map((k) => [k.id, k]));
  const openFindings = openFindingsCount(summary);
  const resourcesAffected = resourcesWithFindings(summary);
  const inventoryTotal = Number(kpisById.total_resources?.value ?? 0);
  const withSavings = Number(summary?.with_savings_findings ?? 0);
  const excluded = excludedFindingsSummary(summary);
  const excludedGaps = excluded.total;
  const estSavings = totalEstimatedSavings(summary);
  const mtdSpend = Number(costSummary?.pretax_total ?? costSummary?.cost_usd_total ?? 0);
  const weeklyAvg = Number(kpisById.weekly_cost?.value ?? 0);
  const projectedMonthly = Number(kpisById.monthly_trend?.value ?? 0);
  const mtdDeltaRaw = portal?.hero_deltas?.mtd_delta_usd;
  const mtdDelta = mtdDeltaRaw == null ? null : Number(mtdDeltaRaw);

  const pipeline = trends?.pipeline_actions_by_status || trends?.actions_by_status || {};
  const proposed = Number(pipeline.proposed ?? 0);
  const approved = Number(pipeline.approved ?? 0);
  const executed = Number(pipeline.executed ?? trends?.executed_actions ?? 0);

  return {
    openFindings,
    resourcesAffected,
    inventoryTotal,
    withSavings,
    excludedGaps,
    estSavings,
    mtdSpend,
    weeklyAvg,
    projectedMonthly,
    mtdDelta,
    proposed,
    approved,
    executed,
    currency: currency || costSummary?.billing_currency || 'CAD',
  };
}

export function sevClassName(severity) {
  const key = String(severity || 'MEDIUM').toLowerCase();
  if (key === 'critical') return 'sev sev-critical';
  if (key === 'high') return 'sev sev-high';
  if (key === 'medium') return 'sev sev-medium';
  return 'sev sev-low';
}
