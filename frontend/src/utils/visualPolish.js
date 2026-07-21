/** Shared helpers for dashboard charts, heat maps, and trend badges. */

export function costToneClass(amount) {
  const cost = Number(amount) || 0;
  if (cost > 1000) return 'danger';
  if (cost > 500) return 'warning';
  if (cost > 100) return 'caution';
  return 'normal';
}

export function barColorByPct(pct) {
  if (pct > 40) return 'var(--danger)';
  if (pct > 20) return 'var(--warning)';
  if (pct > 10) return 'var(--primary)';
  return 'var(--success)';
}

export function increaseColorClass(pct) {
  if (pct >= 50) return 'cost-change-cell__amount--high';
  if (pct >= 20) return 'cost-change-cell__amount--med';
  return 'cost-change-cell__amount--low';
}

export function sparklinePoints(dailyPoints, count = 7) {
  const rows = (dailyPoints || [])
    .map((p) => ({
      date: String(p.date || '').slice(0, 10),
      cost: Number(p.cost_billing ?? p.cost_usd ?? p.cost ?? 0),
    }))
    .filter((p) => p.date);
  return rows.slice(-count);
}

export function anomalyDays(dailyPoints, factor = 1.5) {
  const rows = sparklinePoints(dailyPoints, 30);
  if (rows.length < 3) return [];
  const avg = rows.reduce((s, r) => s + r.cost, 0) / rows.length;
  if (avg <= 0) return [];
  return rows.filter((r) => r.cost > avg * factor);
}

export function mergeForecastSeries(dailyChart, forecastDailyPoints = []) {
  if (!dailyChart?.length) return dailyChart;

  const forecastByDate = Object.fromEntries(
    (forecastDailyPoints || [])
      .map((p) => {
        const date = String(p.date || '').slice(0, 10);
        const cost = Number(p.cost_billing ?? p.cost ?? p.cost_usd ?? 0);
        return date ? [date, cost] : null;
      })
      .filter(Boolean),
  );

  if (!Object.keys(forecastByDate).length) return dailyChart;

  const merged = dailyChart.map((row) => {
    const date = String(row.date || '').slice(0, 10);
    const forecast = forecastByDate[date];
    return forecast != null ? { ...row, forecast } : row;
  });

  const knownDates = new Set(merged.map((row) => String(row.date || '').slice(0, 10)));
  for (const [date, forecast] of Object.entries(forecastByDate)) {
    if (!knownDates.has(date)) {
      merged.push({ date, cost: null, forecast });
    }
  }

  return merged.sort((a, b) => String(a.date).localeCompare(String(b.date)));
}

export const CHART_RANK_COLORS = [
  'var(--primary)',
  '#0ea5e9',
  '#38bdf8',
  '#6366f1',
  '#8b5cf6',
  '#22c55e',
  '#f59e0b',
  '#94a3b8',
];

export const KPI_CARD_TYPE = {
  weekly_cost: 'cost',
  monthly_trend: 'cost',
  estimated_savings: 'savings',
  open_findings: 'warning',
  resources_degraded: 'warning',
  resources_unavailable: 'danger',
  advisor_findings: 'advisor',
  total_resources: 'cost',
};
