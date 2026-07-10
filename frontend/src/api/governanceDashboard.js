/**
 * API client for governance-related endpoints.
 */
import api from './client';

const DEFAULT_QUOTA_LOCATION = 'eastus';

export async function fetchTagComplianceScore(subscriptionId, requiredTags) {
  const { data } = await api.get(`/tag-compliance/score/${encodeURIComponent(subscriptionId)}`, {
    params: requiredTags?.length ? { required_tags: requiredTags } : {},
  });
  return data;
}

export async function fetchTagComplianceGroups(subscriptionId, requiredTags) {
  const { data } = await api.get(`/tag-compliance/groups/${encodeURIComponent(subscriptionId)}`, {
    params: requiredTags?.length ? { required_tags: requiredTags } : {},
  });
  return data;
}

export async function fetchBudgets(subscriptionId) {
  const { data } = await api.get('/budgets', {
    params: { subscription_id: subscriptionId },
  });
  return data;
}

export async function fetchSecurityPosture(subscriptionId) {
  const { data } = await api.get(`/security-posture/${encodeURIComponent(subscriptionId)}`);
  return data;
}

export async function fetchQuotaSummary(subscriptionId, location = DEFAULT_QUOTA_LOCATION) {
  const { data } = await api.get(`/quota/${encodeURIComponent(subscriptionId)}/all`, {
    params: { location },
  });
  return data;
}
