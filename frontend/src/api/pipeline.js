import api from './client';

export const fetchPipelineServices = () =>
  api.get('/pipeline/services').then((r) => r.data);

export const fetchPipelineRouting = () =>
  api.get('/pipeline/routing').then((r) => r.data);

export const fetchPipelineStatus = (subscriptionId) =>
  api.get('/pipeline/status', {
    params: subscriptionId ? { subscription_id: subscriptionId } : undefined,
  }).then((r) => r.data);

export const triggerPipelineRun = (subscriptionId, { skipMetrics = false } = {}) =>
  api.post(`/pipeline/run/${encodeURIComponent(subscriptionId)}`, null, {
    params: { skip_metrics: skipMetrics },
  }).then((r) => r.data);

export const fetchResourceAssessment = (resourceId) =>
  api.get(`/pipeline/resources/${encodeURIComponent(resourceId)}/assessment`).then((r) => r.data);
