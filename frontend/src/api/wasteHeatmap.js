/**
 * API client for Waste Heatmap — wraps /idle-resources/sweep and /idle-resources/summary.
 */
import api from './client';

export async function fetchIdleSweep(subscriptionId, params = {}) {
  const { severity, category, include_resolved = false, limit = 2000 } = params;
  const { data } = await api.get(`/idle-resources/sweep/${encodeURIComponent(subscriptionId)}`, {
    params: {
      include_resolved,
      limit,
      ...(severity ? { severity } : {}),
      ...(category ? { category } : {}),
    },
  });
  return data;
}

export async function fetchIdleSummary(subscriptionId) {
  const { data } = await api.get(`/idle-resources/summary/${encodeURIComponent(subscriptionId)}`);
  return data;
}
