/**
 * API client for Waste Heatmap — wraps /idle-resources/sweep and /idle-resources/summary.
 * No separate backend router needed; the heatmap is derived from idle_resources data.
 */

const BASE = '/api';

export async function fetchIdleSweep(subscriptionId, params = {}) {
  const { severity, category, include_resolved = false } = params;
  const qs = new URLSearchParams({ include_resolved: String(include_resolved) });
  if (severity) qs.set('severity', severity);
  if (category) qs.set('category', category);
  const res = await fetch(`${BASE}/idle-resources/sweep/${encodeURIComponent(subscriptionId)}?${qs}`);
  if (!res.ok) throw new Error(`Idle sweep failed: ${res.status}`);
  return res.json();
}

export async function fetchIdleSummary(subscriptionId) {
  const res = await fetch(`${BASE}/idle-resources/summary/${encodeURIComponent(subscriptionId)}`);
  if (!res.ok) throw new Error(`Idle summary failed: ${res.status}`);
  return res.json();
}
