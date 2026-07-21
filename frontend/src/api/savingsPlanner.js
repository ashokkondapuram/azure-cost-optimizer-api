import api from './client';

export async function fetchSavingsEstimate(subscriptionId, params = {}) {
  const { lookback_days = 30, categories, include_live_azure = true } = params;
  const { data } = await api.get(`/savings-planner/estimate/${encodeURIComponent(subscriptionId)}`, {
    params: {
      lookback_days,
      include_live_azure,
      ...(categories?.length ? { categories: categories.join(',') } : {}),
    },
  });
  return data;
}

export async function syncSavingsPlanner(subscriptionId, params = {}) {
  const { lookback_days = 30, categories, trigger_advisor_generate = true } = params;
  const { data } = await api.post(
    `/savings-planner/sync/${encodeURIComponent(subscriptionId)}`,
    null,
    {
      params: {
        lookback_days,
        trigger_advisor_generate,
        ...(categories?.length ? { categories: categories.join(',') } : {}),
      },
    },
  );
  return data;
}
