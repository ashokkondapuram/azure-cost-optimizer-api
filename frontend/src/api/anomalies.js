/**
 * API client for /anomalies endpoints.
 * Mirrors the FastAPI router at app/routers/cost_anomaly.py
 */

const BASE = '/api';

/**
 * Fetch daily cost time-series + anomaly flags.
 * GET /anomalies/daily/{subscriptionId}
 */
export async function fetchDailyAnomalies(subscriptionId, params = {}) {
  const {
    window_days = 30,
    threshold_sigma = 2.0,
    lookback_days = 7,
  } = params;

  const qs = new URLSearchParams({
    window_days: String(window_days),
    threshold_sigma: String(threshold_sigma),
    lookback_days: String(lookback_days),
  });

  const res = await fetch(`${BASE}/anomalies/daily/${encodeURIComponent(subscriptionId)}?${qs}`);
  if (!res.ok) throw new Error(`Daily anomalies request failed: ${res.status}`);
  return res.json();
}

/**
 * Fetch per-service anomaly breakdown.
 * GET /anomalies/service/{subscriptionId}
 */
export async function fetchServiceAnomalies(subscriptionId, params = {}) {
  const {
    window_days = 21,
    threshold_sigma = 2.5,
  } = params;

  const qs = new URLSearchParams({
    window_days: String(window_days),
    threshold_sigma: String(threshold_sigma),
  });

  const res = await fetch(`${BASE}/anomalies/service/${encodeURIComponent(subscriptionId)}?${qs}`);
  if (!res.ok) throw new Error(`Service anomalies request failed: ${res.status}`);
  return res.json();
}
