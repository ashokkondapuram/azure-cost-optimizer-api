/**
 * API client for governance-related endpoints.
 * Pulls from /tag-compliance, /budgets, /quota, /security-posture
 */
const BASE = '/api';

export async function fetchTagComplianceScore(subscriptionId, requiredTags) {
  const qs = new URLSearchParams();
  if (requiredTags?.length) requiredTags.forEach((t) => qs.append('required_tags', t));
  const res = await fetch(`${BASE}/tag-compliance/score/${encodeURIComponent(subscriptionId)}?${qs}`);
  if (!res.ok) throw new Error(`Tag compliance failed: ${res.status}`);
  return res.json();
}

export async function fetchTagComplianceGroups(subscriptionId, requiredTags) {
  const qs = new URLSearchParams();
  if (requiredTags?.length) requiredTags.forEach((t) => qs.append('required_tags', t));
  const res = await fetch(`${BASE}/tag-compliance/groups/${encodeURIComponent(subscriptionId)}?${qs}`);
  if (!res.ok) throw new Error(`Tag groups failed: ${res.status}`);
  return res.json();
}

export async function fetchBudgets(subscriptionId) {
  const qs = new URLSearchParams({ subscription_id: subscriptionId });
  const res = await fetch(`${BASE}/costs/budgets?${qs}`);
  if (!res.ok) throw new Error(`Budgets failed: ${res.status}`);
  return res.json();
}

export async function fetchSecurityPosture(subscriptionId) {
  const qs = new URLSearchParams({ subscription_id: subscriptionId });
  const res = await fetch(`${BASE}/security-posture/summary?${qs}`);
  if (!res.ok) throw new Error(`Security posture failed: ${res.status}`);
  return res.json();
}

export async function fetchQuotaSummary(subscriptionId) {
  const qs = new URLSearchParams({ subscription_id: subscriptionId });
  const res = await fetch(`${BASE}/quota/summary?${qs}`);
  if (!res.ok) throw new Error(`Quota summary failed: ${res.status}`);
  return res.json();
}
