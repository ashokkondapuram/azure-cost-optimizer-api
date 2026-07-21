import { buildResourceSpendTrendChart, hasSpendTrendData } from './drawerResourceCostTrend';

describe('drawerResourceCostTrend', () => {
  test('buildResourceSpendTrendChart maps dated points', () => {
    const chart = buildResourceSpendTrendChart([
      { date: '2026-07-10', cost: 12.5 },
      { date: '2026-07-11', cost: 8 },
    ]);
    expect(chart).toHaveLength(2);
    expect(chart[0].dateLabel).toMatch(/Jul/);
    expect(chart[1].cost).toBe(8);
  });

  test('hasSpendTrendData detects non-zero spend', () => {
    const chart = buildResourceSpendTrendChart([{ date: '2026-07-10', cost: 0 }, { date: '2026-07-11', cost: 2 }]);
    expect(hasSpendTrendData(chart)).toBe(true);
    expect(hasSpendTrendData([{ date: '2026-07-10', cost: 0 }])).toBe(false);
  });
});
