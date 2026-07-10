/**
 * API client for /savings endpoints (optimization timeline).
 */
import api from './client';

export async function fetchMonthOverMonth(subscriptionId, months_back = 6) {
  const { data } = await api.get(`/savings/month-over-month/${encodeURIComponent(subscriptionId)}`, {
    params: { months_back },
  });
  return data;
}

export async function fetchServiceBreakdown(subscriptionId, base_month, compare_month) {
  const { data } = await api.get(`/savings/service-breakdown/${encodeURIComponent(subscriptionId)}`, {
    params: { base_month, compare_month },
  });
  return data;
}
