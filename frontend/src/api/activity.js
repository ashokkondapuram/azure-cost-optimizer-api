import api from './client';

export const fetchFindingActivity = (findingId, subscriptionId) =>
  api.get(`/activity/finding/${findingId}`, { params: { subscription_id: subscriptionId } }).then((r) => r.data);

export const logFindingActivity = (body) =>
  api.post('/activity/log', body).then((r) => r.data);
