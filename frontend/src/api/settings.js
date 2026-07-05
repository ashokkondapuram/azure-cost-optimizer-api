import api from './client';

export const fetchAllSettings = () => api.get('/settings').then((r) => r.data);

export const fetchSettingsCategory = (category) =>
  api.get(`/settings/${category}`).then((r) => r.data);

export const saveAzureSettings = (body) =>
  api.post('/settings/azure', body).then((r) => r.data);

export const saveDatabaseSettings = (body) =>
  api.post('/settings/database', body).then((r) => r.data);

export const saveApplicationSettings = (body) =>
  api.post('/settings/application', body).then((r) => r.data);

export const saveKubernetesSettings = (body) =>
  api.post('/settings/kubernetes', body).then((r) => r.data);

export const testAzureSettings = (body = {}) =>
  api.post('/settings/azure/test', body).then((r) => r.data);

export const testDatabaseSettings = (body = {}) =>
  api.post('/settings/database/test', body).then((r) => r.data);

export const saveAiSettings = (body) =>
  api.post('/settings/ai', body).then((r) => r.data);

export const testAiSettings = (body = {}) =>
  api.post('/settings/ai/test', body).then((r) => r.data);

export const reloadSettings = () =>
  api.post('/settings/reload').then((r) => r.data);

export const fetchSettingsStatus = () =>
  api.get('/settings/status').then((r) => r.data);

export const applyDatabaseSettings = () =>
  api.post('/settings/database/apply').then((r) => r.data);
