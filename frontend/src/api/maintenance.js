import api from './client';

export async function fetchPlannedMaintenance(subscriptionId, params = {}) {
  const { upcoming_only = true, force_refresh = false } = params;
  const { data } = await api.get(
    `/maintenance/${encodeURIComponent(subscriptionId)}/planned`,
    { params: { upcoming_only, force_refresh } },
  );
  return data;
}

export async function requestMaintenanceSync(subscriptionId) {
  const { data } = await api.post(
    `/maintenance/${encodeURIComponent(subscriptionId)}/sync`,
  );
  return data;
}

export async function fetchMaintenanceSummary(subscriptionId) {
  const { data } = await api.get(
    `/maintenance/${encodeURIComponent(subscriptionId)}/summary`,
  );
  return data;
}
