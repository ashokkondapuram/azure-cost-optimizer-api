/**
 * API client for Tag Compliance — wraps /tag-compliance/score and /tag-compliance/groups.
 */
import api from './client';

export async function fetchComplianceScore(subscriptionId, params = {}) {
  const {
    required_tags = ['environment', 'owner', 'cost-center'],
    resource_group,
    resource_type,
    limit = 2000,
  } = params;
  const { data } = await api.get(`/tag-compliance/score/${encodeURIComponent(subscriptionId)}`, {
    params: {
      required_tags,
      limit,
      ...(resource_group ? { resource_group } : {}),
      ...(resource_type ? { resource_type } : {}),
    },
  });
  return data;
}

export async function fetchComplianceGroups(subscriptionId, required_tags = ['environment', 'owner', 'cost-center']) {
  const { data } = await api.get(`/tag-compliance/groups/${encodeURIComponent(subscriptionId)}`, {
    params: { required_tags },
  });
  return data;
}
