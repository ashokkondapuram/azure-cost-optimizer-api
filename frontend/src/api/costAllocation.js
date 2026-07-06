/**
 * API client for cost allocation / breakdown endpoints.
 * Mirrors app/routers/costs.py (by-service, by-resource-type, summary, by-resource)
 */
const BASE = '/api';

export async function fetchCostByService(subscriptionId, params = {}) {
  const { timeframe = 'MonthToDate', from_date, to_date } = params;
  const qs = new URLSearchParams({ subscription_id: subscriptionId, timeframe });
  if (from_date) qs.set('from_date', from_date);
  if (to_date) qs.set('to_date', to_date);
  const res = await fetch(`${BASE}/costs/by-service?${qs}`);
  if (!res.ok) throw new Error(`By-service failed: ${res.status}`);
  return res.json();
}

export async function fetchCostByResourceType(subscriptionId, timeframe = 'MonthToDate') {
  const qs = new URLSearchParams({ subscription_id: subscriptionId, timeframe });
  const res = await fetch(`${BASE}/costs/by-resource-type?${qs}`);
  if (!res.ok) throw new Error(`By-resource-type failed: ${res.status}`);
  return res.json();
}

export async function fetchCostSummary(subscriptionId, params = {}) {
  const { timeframe = 'MonthToDate', from_date, to_date } = params;
  const qs = new URLSearchParams({ subscription_id: subscriptionId, timeframe });
  if (from_date) qs.set('from_date', from_date);
  if (to_date) qs.set('to_date', to_date);
  const res = await fetch(`${BASE}/costs/summary?${qs}`);
  if (!res.ok) throw new Error(`Summary failed: ${res.status}`);
  return res.json();
}

export async function fetchCostByResource(subscriptionId, timeframe = 'MonthToDate') {
  const qs = new URLSearchParams({ subscription_id: subscriptionId, timeframe });
  const res = await fetch(`${BASE}/costs/by-resource?${qs}`);
  if (!res.ok) throw new Error(`By-resource failed: ${res.status}`);
  return res.json();
}

export async function fetchCostByResourceGroup(subscriptionId, resourceGroup, params = {}) {
  const { timeframe = 'MonthToDate', from_date, to_date } = params;
  const qs = new URLSearchParams({ subscription_id: subscriptionId, resource_group: resourceGroup, timeframe });
  if (from_date) qs.set('from_date', from_date);
  if (to_date) qs.set('to_date', to_date);
  const res = await fetch(`${BASE}/costs/resource-group?${qs}`);
  if (!res.ok) throw new Error(`By-resource-group failed: ${res.status}`);
  return res.json();
}
