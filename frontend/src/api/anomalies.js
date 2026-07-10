/**
 * API client for /anomalies endpoints.
 */
import api from './client';

export async function fetchDailyAnomalies(subscriptionId, params = {}) {
  const {
    window_days = 30,
    threshold_sigma = 2.0,
    lookback_days = 7,
  } = params;
  const { data } = await api.get(`/anomalies/daily/${encodeURIComponent(subscriptionId)}`, {
    params: { window_days, threshold_sigma, lookback_days },
  });
  return data;
}

export async function fetchServiceAnomalies(subscriptionId, params = {}) {
  const {
    window_days = 21,
    threshold_sigma = 2.5,
  } = params;
  const { data } = await api.get(`/anomalies/service/${encodeURIComponent(subscriptionId)}`, {
    params: { window_days, threshold_sigma },
  });
  return data;
}
