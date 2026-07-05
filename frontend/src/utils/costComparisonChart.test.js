import { buildMtdComparisonSeries } from './costComparisonChart';

describe('buildMtdComparisonSeries', () => {
  const today = new Date();
  const y = today.getFullYear();
  const m = String(today.getMonth() + 1).padStart(2, '0');
  const prior = new Date(y, today.getMonth() - 1, 1);
  const py = prior.getFullYear();
  const pm = String(prior.getMonth() + 1).padStart(2, '0');

  it('builds cumulative MTD series for current and prior month', () => {
    const dailyPoints = [
      { date: `${y}-${m}-01`, cost_usd: 10 },
      { date: `${y}-${m}-02`, cost_usd: 20 },
      { date: `${py}-${pm}-01`, cost_usd: 5 },
      { date: `${py}-${pm}-02`, cost_usd: 15 },
    ];

    const { series } = buildMtdComparisonSeries(dailyPoints);
    expect(series.length).toBeGreaterThanOrEqual(2);
    expect(series[0].mtd).toBe(10);
    expect(series[1].mtd).toBe(30);
    expect(series[0].priorMtd).toBe(5);
    expect(series[1].priorMtd).toBe(20);
  });

  it('returns empty series when no daily points', () => {
    const { series } = buildMtdComparisonSeries([]);
    expect(series).toEqual([]);
  });
});
