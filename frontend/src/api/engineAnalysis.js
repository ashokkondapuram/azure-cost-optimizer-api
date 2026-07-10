/**
 * API client for /engine/analysis endpoints.
 */
import api from './client';

export async function fetchCombinedAnalysis(subscriptionId, params = {}) {
  const {
    tier,
    resource_type,
    min_score,
    exclude_maintenance_hold = true,
    top_n = 20,
  } = params;
  const { data } = await api.get(`/engine/analysis/${encodeURIComponent(subscriptionId)}/combined`, {
    params: {
      exclude_maintenance_hold,
      top_n,
      ...(tier ? { tier } : {}),
      ...(resource_type ? { resource_type } : {}),
      ...(min_score != null ? { min_score } : {}),
    },
  });
  return data;
}

export async function fetchAdvancedScores(subscriptionId, params = {}) {
  const { tier, resource_type, min_score, limit = 50, offset = 0 } = params;
  const { data } = await api.get(`/engine/analysis/${encodeURIComponent(subscriptionId)}/advanced-scores`, {
    params: {
      limit,
      offset,
      ...(tier ? { tier } : {}),
      ...(resource_type ? { resource_type } : {}),
      ...(min_score != null ? { min_score } : {}),
    },
  });
  return data;
}

export async function runEngineAnalysis(subscriptionId, params = {}) {
  const { force_rescore = false, include_maintenance = true, sync_advisor = true } = params;
  const { data } = await api.post(`/engine/analysis/${encodeURIComponent(subscriptionId)}/run`, null, {
    params: { force_rescore, include_maintenance, sync_advisor },
  });
  return data;
}

export async function fetchAiRecommendations(subscriptionId, params = {}) {
  const { force_refresh = false, max_findings } = params;
  const { data } = await api.post(
    `/engine/analysis/${encodeURIComponent(subscriptionId)}/ai-recommendations`,
    null,
    {
      params: {
        force_refresh,
        ...(max_findings != null ? { max_findings } : {}),
      },
    },
  );
  return data;
}
