/**
 * API client for /reservations endpoints.
 */
import api from './client';

export async function fetchReservationAdvisor(subscriptionId, params = {}) {
  const {
    commitment_type = 'all',
    month,
    include_live_azure = true,
  } = params;
  const { data } = await api.get(`/reservations/advisor/${encodeURIComponent(subscriptionId)}`, {
    params: {
      commitment_type,
      include_live_azure,
      ...(month ? { month } : {}),
    },
  });
  return data;
}

export async function syncReservationAdvisor(subscriptionId, { trigger_advisor_generate = false } = {}) {
  const { data } = await api.post(
    `/reservations/sync/${encodeURIComponent(subscriptionId)}`,
    null,
    { params: { trigger_advisor_generate } },
  );
  return data;
}

export async function fetchReservationCoverage(subscriptionId, month) {
  const { data } = await api.get(`/reservations/coverage/${encodeURIComponent(subscriptionId)}`, {
    params: month ? { month } : {},
  });
  return data;
}

export async function fetchReservationRecommendations(subscriptionId, commitmentType = 'all') {
  const { data } = await api.get(`/reservations/recommendations/${encodeURIComponent(subscriptionId)}`, {
    params: { commitment_type: commitmentType },
  });
  return data;
}
