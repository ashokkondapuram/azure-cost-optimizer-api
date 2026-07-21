import api from './client';

export const discoverK8sClusters = (subscriptionId) =>
  api.get('/k8s/clusters/discover', { params: { subscription_id: subscriptionId } }).then((r) => r.data);

export const fetchConnectedK8sClusters = () =>
  api.get('/k8s/clusters').then((r) => r.data);

export const connectK8sCluster = (body) =>
  api.post('/k8s/clusters/connect', body).then((r) => r.data);

export const deployK8sAgent = (clusterId) =>
  api.post(`/k8s/clusters/${clusterId}/deploy-agent`).then((r) => r.data);
