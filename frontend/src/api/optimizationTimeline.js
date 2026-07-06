/**
 * API client for /savings endpoints.
 * Mirrors app/routers/savings_tracker.py
 */

const BASE = '/api';

export async function fetchMonthOverMonth(subscriptionId, months_back = 6) {
  const qs = new URLSearchParams({ months_back: String(months_back) });
  const res = await fetch(`${BASE}/savings/month-over-month/${encodeURIComponent(subscriptionId)}?${qs}`);
  if (!res.ok) throw new Error(`Month-over-month failed: ${res.status}`);
  return res.json();
}

export async function fetchServiceBreakdown(subscriptionId, base_month, compare_month) {
  const qs = new URLSearchParams({ base_month, compare_month });
  const res = await fetch(`${BASE}/savings/service-breakdown/${encodeURIComponent(subscriptionId)}?${qs}`);
  if (!res.ok) throw new Error(`Service breakdown failed: ${res.status}`);
  return res.json();
}
