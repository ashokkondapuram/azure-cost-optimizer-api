/**
 * Demand Forecaster — pulls cost history then projects via linear regression.
 * Uses /savings/month-over-month for historical data (already in the DB)
 * and /costs/summary for the current MTD figure.
 * All forecasting math is done client-side — no dedicated backend route needed.
 */
const BASE = '/api';

export async function fetchForecastData(subscriptionId, monthsBack = 6) {
  const qs = new URLSearchParams({ months_back: String(monthsBack) });
  const res = await fetch(`${BASE}/savings/month-over-month/${encodeURIComponent(subscriptionId)}?${qs}`);
  if (!res.ok) throw new Error(`Forecast data failed: ${res.status}`);
  return res.json();
}

/**
 * Simple weighted linear regression over monthly totals.
 * Returns { slope, intercept, r2, forecast } where forecast is an array
 * of { month, predicted_spend } for the next `horizonMonths` months.
 */
export function computeForecast(timeline, horizonMonths = 3) {
  if (!timeline?.length) return null;
  const n = timeline.length;
  const xs = timeline.map((_, i) => i);
  const ys = timeline.map((t) => t.total_spend ?? 0);

  // Weighted: recent months count more
  const weights = xs.map((x) => 1 + x / n);
  const W = weights.reduce((a, b) => a + b, 0);
  const Wx = weights.reduce((s, w, i) => s + w * xs[i], 0);
  const Wy = weights.reduce((s, w, i) => s + w * ys[i], 0);
  const Wxx = weights.reduce((s, w, i) => s + w * xs[i] ** 2, 0);
  const Wxy = weights.reduce((s, w, i) => s + w * xs[i] * ys[i], 0);

  const denom = W * Wxx - Wx ** 2;
  if (denom === 0) return null;

  const slope = (W * Wxy - Wx * Wy) / denom;
  const intercept = (Wy - slope * Wx) / W;

  // R²
  const yBar = Wy / W;
  const ssTot = weights.reduce((s, w, i) => s + w * (ys[i] - yBar) ** 2, 0);
  const ssRes = weights.reduce((s, w, i) => s + w * (ys[i] - (slope * xs[i] + intercept)) ** 2, 0);
  const r2 = ssTot > 0 ? Math.max(0, 1 - ssRes / ssTot) : 1;

  // Project forward
  const lastMonth = timeline[n - 1].month;
  const forecast = [];
  for (let h = 1; h <= horizonMonths; h++) {
    const [yr, mo] = lastMonth.split('-').map(Number);
    const d = new Date(yr, mo - 1 + h, 1);
    const month = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
    const predicted_spend = Math.max(0, slope * (n - 1 + h) + intercept);
    forecast.push({ month, predicted_spend: Math.round(predicted_spend * 100) / 100, is_forecast: true });
  }

  return { slope, intercept, r2: Math.round(r2 * 1000) / 1000, forecast };
}
