/**
 * API client for /engine/analysis endpoints.
 * Mirrors app/routers/engine_analysis.py
 */

const BASE = '/api';

export async function fetchCombinedAnalysis(subscriptionId, params = {}) {
  const {
    tier,
    resource_type,
    min_score,
    exclude_maintenance_hold = true,
    top_n = 20,
  } = params;
  const qs = new URLSearchParams({ exclude_maintenance_hold: String(exclude_maintenance_hold), top_n: String(top_n) });
  if (tier) qs.set('tier', tier);
  if (resource_type) qs.set('resource_type', resource_type);
  if (min_score != null) qs.set('min_score', String(min_score));
  const res = await fetch(`${BASE}/engine/analysis/${encodeURIComponent(subscriptionId)}/combined?${qs}`);
  if (!res.ok) throw new Error(`Combined analysis failed: ${res.status}`);
  return res.json();
}

export async function fetchAdvancedScores(subscriptionId, params = {}) {
  const { tier, resource_type, min_score, limit = 50, offset = 0 } = params;
  const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (tier) qs.set('tier', tier);
  if (resource_type) qs.set('resource_type', resource_type);
  if (min_score != null) qs.set('min_score', String(min_score));
  const res = await fetch(`${BASE}/engine/analysis/${encodeURIComponent(subscriptionId)}/advanced-scores?${qs}`);
  if (!res.ok) throw new Error(`Advanced scores failed: ${res.status}`);
  return res.json();
}

export async function runEngineAnalysis(subscriptionId, params = {}) {
  const { force_rescore = false, include_maintenance = true, sync_advisor = true } = params;
  const qs = new URLSearchParams({
    force_rescore: String(force_rescore),
    include_maintenance: String(include_maintenance),
    sync_advisor: String(sync_advisor),
  });
  const res = await fetch(`${BASE}/engine/analysis/${encodeURIComponent(subscriptionId)}/run?${qs}`, { method: 'POST' });
  if (!res.ok) throw new Error(`Engine run failed: ${res.status}`);
  return res.json();
}
