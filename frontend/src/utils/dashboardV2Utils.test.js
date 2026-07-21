import {
  resolveDashboardMetrics,
  severityRows,
  categoryRows,
  sourceChipCounts,
  findingsLeadText,
  savingsPctOfMtd,
  normalizeDashboardOverview,
  hasDashboardOverviewData,
} from './dashboardV2Utils';

describe('dashboardV2Utils', () => {
  test('resolveDashboardMetrics uses API values without prototype fallbacks', () => {
    const metrics = resolveDashboardMetrics({
      summary: {
        open_findings: 0,
        resources_with_findings: 0,
        with_savings_findings: 0,
        excluded: { total: 0 },
        total_estimated_savings_usd: 0,
        by_severity: {},
        by_category: {},
        by_source: {},
      },
      portal: {
        kpis: [
          { id: 'total_resources', value: 120 },
          { id: 'weekly_cost', value: 0 },
          { id: 'monthly_trend', value: 0 },
        ],
        hero_deltas: { mtd_delta_usd: null },
      },
      costSummary: { pretax_total: 0, billing_currency: 'CAD' },
      currency: 'CAD',
      trends: { pipeline_actions_by_status: { proposed: 0, approved: 0, executed: 0 } },
    });

    expect(metrics.openFindings).toBe(0);
    expect(metrics.resourcesAffected).toBe(0);
    expect(metrics.estSavings).toBe(0);
    expect(metrics.weeklyAvg).toBe(0);
    expect(metrics.projectedMonthly).toBe(0);
    expect(metrics.mtdDelta).toBeNull();
    expect(metrics.proposed).toBe(0);
  });

  test('severityRows returns zeros when summary is empty', () => {
    const rows = severityRows({ by_severity: {} });
    expect(rows.every((row) => row.count === 0)).toBe(true);
  });

  test('categoryRows returns empty list without fallback categories', () => {
    expect(categoryRows({ by_category: {} })).toEqual([]);
  });

  test('sourceChipCounts returns zero counts for empty summary', () => {
    const chips = sourceChipCounts({ by_source: {} });
    expect(chips.find((c) => c.id === 'engine')?.count).toBe(0);
    expect(chips.find((c) => c.id === 'advisor')?.count).toBe(0);
  });

  test('findingsLeadText reflects zero counts', () => {
    expect(findingsLeadText({ open_findings: 0, by_source: {} }, 'all', 0))
      .toBe('0 open issues across 0 resources');
  });

  test('savingsPctOfMtd handles zero mtd', () => {
    expect(savingsPctOfMtd(100, 0)).toBeNull();
    expect(savingsPctOfMtd(50, 200)).toBe(25);
  });

  test('normalizeDashboardOverview coerces partial payloads', () => {
    const normalized = normalizeDashboardOverview({
      subscription_id: 'sub-1',
      cost: { summary: { pretax_total: 10 } },
    });
    expect(normalized.subscription_id).toBe('sub-1');
    expect(normalized.cost.summary.pretax_total).toBe(10);
    expect(normalized.cost.daily.points).toEqual([]);
    expect(normalized.optimization.recommendations.items).toEqual([]);
  });

  test('hasDashboardOverviewData accepts sync and inventory hints', () => {
    expect(hasDashboardOverviewData(null)).toBe(false);
    expect(hasDashboardOverviewData({ subscription_id: 'sub-1' })).toBe(true);
    expect(hasDashboardOverviewData({ sync: { inventory: { resource_count: 3 } } })).toBe(true);
    expect(hasDashboardOverviewData({ inventory: { counts: { inventory_total: 2 } } })).toBe(true);
  });
});
