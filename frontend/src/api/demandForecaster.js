/**
 * Demand Forecaster — monthly history and forecast from Azure Cost Management.
 */
import api from './client';

export async function fetchDemandForecast(subscriptionId, monthsBack = 6) {
  const { data } = await api.get('/costs/demand-forecast', {
    params: {
      subscription_id: subscriptionId,
      months_back: monthsBack,
    },
  });
  return data;
}

/** Merge historical timeline + Azure forecast rows for charting. */
export function buildForecastChartData(timeline = [], forecast = []) {
  const hist = (timeline || []).map((t) => ({
    month: t.month,
    total_spend: t.total_spend,
    predicted_spend: null,
    is_forecast: false,
  }));

  const fore = (forecast || []).map((row) => ({
    month: row.month,
    total_spend: null,
    predicted_spend: row.predicted_spend,
    is_forecast: true,
  }));

  const months = new Set([...hist, ...fore].map((r) => r.month));
  const byMonth = new Map();
  for (const row of [...hist, ...fore]) {
    const existing = byMonth.get(row.month) || {
      month: row.month,
      total_spend: null,
      predicted_spend: null,
      is_forecast: false,
    };
    if (row.total_spend != null) existing.total_spend = row.total_spend;
    if (row.predicted_spend != null) {
      existing.predicted_spend = row.predicted_spend;
      existing.is_forecast = true;
    }
    byMonth.set(row.month, existing);
  }

  return [...months]
    .sort()
    .map((month) => byMonth.get(month))
    .filter(Boolean);
}
