/**
 * API client for Tag Compliance — wraps /tag-compliance/score and /tag-compliance/groups.
 */

const BASE = '/api';

export async function fetchComplianceScore(subscriptionId, params = {}) {
  const { required_tags = ['environment', 'owner', 'cost-center'], resource_group, resource_type } = params;
  const qs = new URLSearchParams();
  required_tags.forEach((t) => qs.append('required_tags', t));
  if (resource_group) qs.set('resource_group', resource_group);
  if (resource_type) qs.set('resource_type', resource_type);
  const res = await fetch(`${BASE}/tag-compliance/score/${encodeURIComponent(subscriptionId)}?${qs}`);
  if (!res.ok) throw new Error(`Tag compliance score failed: ${res.status}`);
  return res.json();
}

export async function fetchComplianceGroups(subscriptionId, required_tags = ['environment', 'owner', 'cost-center']) {
  const qs = new URLSearchParams();
  required_tags.forEach((t) => qs.append('required_tags', t));
  const res = await fetch(`${BASE}/tag-compliance/groups/${encodeURIComponent(subscriptionId)}?${qs}`);
  if (!res.ok) throw new Error(`Tag compliance groups failed: ${res.status}`);
  return res.json();
}
