/**
 * API client for cost allocation / breakdown endpoints.
 */
import api from './client';

export async function fetchCostByService(subscriptionId, params = {}) {
  const { timeframe = 'MonthToDate', from_date, to_date } = params;
  const { data } = await api.get('/costs/by-service', {
    params: {
      subscription_id: subscriptionId,
      timeframe,
      ...(from_date ? { from_date } : {}),
      ...(to_date ? { to_date } : {}),
    },
  });
  return data;
}

export async function fetchCostByResourceType(subscriptionId, timeframe = 'MonthToDate') {
  const { data } = await api.get('/costs/by-resource-type', {
    params: { subscription_id: subscriptionId, timeframe },
  });
  return data;
}

export async function fetchCostSummary(subscriptionId, params = {}) {
  const { timeframe = 'MonthToDate', from_date, to_date } = params;
  const { data } = await api.get('/costs/summary', {
    params: {
      subscription_id: subscriptionId,
      timeframe,
      ...(from_date ? { from_date } : {}),
      ...(to_date ? { to_date } : {}),
    },
  });
  return data;
}

export async function fetchCostByResource(subscriptionId, timeframe = 'MonthToDate') {
  const { data } = await api.get('/costs/by-resource', {
    params: { subscription_id: subscriptionId, timeframe },
  });
  return data;
}

export async function fetchCostByResourceGroup(subscriptionId, resourceGroup, params = {}) {
  const { timeframe = 'MonthToDate', from_date, to_date } = params;
  const { data } = await api.get('/costs/resource-group', {
    params: {
      subscription_id: subscriptionId,
      resource_group: resourceGroup,
      timeframe,
      ...(from_date ? { from_date } : {}),
      ...(to_date ? { to_date } : {}),
    },
  });
  return data;
}
