import {
  buildWhatIfComparisonRows,
  impactDirectionLabel,
  projectWhatIfCosts,
  resolveWhatIfMonthlyCost,
} from './whatIfUtils';

describe('whatIfUtils', () => {
  const scenario = {
    action: 'downgrade',
    costImpact: { savingsPercent: 25 },
    performanceImpact: {
      before: 'CPU at 12% on current SKU.',
      after: 'Lower SKU with less headroom.',
      direction: 'at_risk',
    },
    reliabilityImpact: {
      before: 'Meets SLA today.',
      after: 'SLA margin narrows at peak.',
      direction: 'at_risk',
    },
  };

  test('projectWhatIfCosts uses finding savings when available', () => {
    const result = projectWhatIfCosts({
      scenario,
      monthlyCost: 400,
      findingSavings: 100,
      currency: 'CAD',
    });
    expect(result.before).toBe(400);
    expect(result.after).toBe(300);
    expect(result.savings).toBe(100);
  });

  test('projectWhatIfCosts falls back to savings percent', () => {
    const result = projectWhatIfCosts({
      scenario,
      monthlyCost: 200,
      findingSavings: 0,
    });
    expect(result.savings).toBe(50);
    expect(result.after).toBe(150);
  });

  test('resolveWhatIfMonthlyCost prefers finding evidence', () => {
    expect(resolveWhatIfMonthlyCost({
      monthlyResourceCost: 10,
      finding: { evidence: { monthly_cost: 250 } },
    })).toBe(250);
  });

  test('buildWhatIfComparisonRows returns cost performance reliability', () => {
    const rows = buildWhatIfComparisonRows({
      scenario,
      monthlyCost: 400,
      findingSavings: 100,
      currency: 'CAD',
    });
    expect(rows).toHaveLength(3);
    expect(rows[0].label).toBe('Cost');
    expect(rows[1].label).toBe('Performance');
    expect(rows[2].label).toBe('Reliability');
    expect(rows[0].after).toContain('300');
  });

  test('impactDirectionLabel maps known directions', () => {
    expect(impactDirectionLabel('improved')).toBe('Improves');
    expect(impactDirectionLabel('at_risk')).toBe('At risk');
  });
});
