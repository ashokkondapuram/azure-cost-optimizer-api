import { formatCurrency } from './format';

const DIRECTION_LABELS = {
  improved: 'Improves',
  degraded: 'Degrades',
  at_risk: 'At risk',
  unchanged: 'Unchanged',
};

const DIRECTION_CLASS = {
  improved: 'wiz-whatif__direction--improved',
  degraded: 'wiz-whatif__direction--degraded',
  at_risk: 'wiz-whatif__direction--risk',
  unchanged: 'wiz-whatif__direction--unchanged',
};

export function impactDirectionLabel(direction) {
  return DIRECTION_LABELS[String(direction || 'unchanged').toLowerCase()] || 'Unchanged';
}

export function impactDirectionClass(direction) {
  return DIRECTION_CLASS[String(direction || 'unchanged').toLowerCase()] || DIRECTION_CLASS.unchanged;
}

/** Resolve monthly cost before change from finding + resource context. */
export function resolveWhatIfMonthlyCost({ monthlyResourceCost = 0, finding = null } = {}) {
  const fromFinding = finding?.estimated_monthly_cost
    ?? finding?.evidence?.monthly_cost
    ?? finding?.evidence?.cost?.monthlyActualCost;
  const value = Number(fromFinding ?? monthlyResourceCost ?? 0);
  return Number.isFinite(value) && value > 0 ? value : 0;
}

/** Project before/after monthly cost from scenario and finding savings. */
export function projectWhatIfCosts({
  scenario,
  monthlyCost = 0,
  findingSavings = 0,
  currency = 'CAD',
}) {
  const before = Math.max(0, Number(monthlyCost) || 0);
  const savingsPercent = Number(scenario?.costImpact?.savingsPercent) || 0;
  let savings = Math.max(0, Number(findingSavings) || 0);

  if (savings <= 0 && before > 0 && savingsPercent > 0) {
    savings = before * (savingsPercent / 100);
  }

  const after = Math.max(0, before - savings);
  const hasCost = before > 0 || savings > 0;

  return {
    before,
    after,
    savings,
    hasCost,
    beforeLabel: hasCost ? formatCurrency(before, { currency, decimals: 0 }) : '—',
    afterLabel: hasCost ? formatCurrency(after, { currency, decimals: 0 }) : '—',
    savingsLabel: savings > 0 ? formatCurrency(savings, { currency, decimals: 0 }) : '—',
  };
}

/** Build comparison rows for cost, performance, and reliability. */
export function buildWhatIfComparisonRows({
  scenario,
  monthlyCost = 0,
  findingSavings = 0,
  currency = 'CAD',
  performanceMetrics = [],
}) {
  if (!scenario) return [];

  const costs = projectWhatIfCosts({ scenario, monthlyCost, findingSavings, currency });
  const perf = scenario.performanceImpact || {};
  const rel = scenario.reliabilityImpact || {};

  const perfBefore = perf.before
    || (performanceMetrics.length
      ? `Current: ${performanceMetrics.slice(0, 2).map((m) => m.formatted || m.label).join(' · ')}`
      : 'Current utilization and capacity from live metrics.');

  const rows = [
    {
      id: 'cost',
      label: 'Cost',
      before: costs.beforeLabel,
      after: costs.afterLabel,
      detail: costs.savings > 0 ? `${costs.savingsLabel}/mo estimated savings` : scenario.costImpact?.description,
      direction: costs.savings > 0 ? 'improved' : 'unchanged',
    },
    {
      id: 'performance',
      label: 'Performance',
      before: perfBefore,
      after: perf.after || scenario.proposedState?.description || '—',
      direction: perf.direction || 'unchanged',
    },
    {
      id: 'reliability',
      label: 'Reliability',
      before: rel.before || scenario.currentState?.description || '—',
      after: rel.after || scenario.proposedState?.description || '—',
      direction: rel.direction || 'unchanged',
    },
  ];

  return rows;
}

export function extractPerformanceMetricsFromFinding(finding) {
  const metrics = finding?.evidence?.optimization_metrics?.performance;
  return Array.isArray(metrics) ? metrics.filter((m) => m.status !== 'unavailable') : [];
}
