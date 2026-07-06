/**
 * API client for /reservations endpoints.
 * Mirrors app/routers/reservation_coverage.py
 */
const BASE = '/api';

export async function fetchReservationCoverage(subscriptionId, month) {
  const qs = new URLSearchParams();
  if (month) qs.set('month', month);
  const res = await fetch(`${BASE}/reservations/coverage/${encodeURIComponent(subscriptionId)}?${qs}`);
  if (!res.ok) throw new Error(`Coverage failed: ${res.status}`);
  return res.json();
}

export async function fetchReservationRecommendations(subscriptionId, commitmentType = 'all') {
  const qs = new URLSearchParams({ commitment_type: commitmentType });
  const res = await fetch(`${BASE}/reservations/recommendations/${encodeURIComponent(subscriptionId)}?${qs}`);
  if (!res.ok) throw new Error(`Recommendations failed: ${res.status}`);
  return res.json();
}
