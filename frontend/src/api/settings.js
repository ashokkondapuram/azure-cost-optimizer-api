import api from './client';
import { withTimeout } from '../utils/apiTimeout';

const NAV_ACCESS_TIMEOUT_MS = 15_000;

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

export const reloadSettings = () =>
  api.post('/settings/reload').then((r) => r.data);

export const fetchSettingsStatus = () =>
  api.get('/settings/status').then((r) => r.data);

export const applyDatabaseSettings = () =>
  api.post('/settings/database/apply').then((r) => r.data);

export const fetchNavAccessMe = () =>
  withTimeout(
    api.get('/settings/nav-access/me').then((r) => r.data),
    NAV_ACCESS_TIMEOUT_MS,
    'Navigation access check timed out',
  );

export const fetchNavAccessPolicy = () =>
  api.get('/settings/nav-access/policy').then((r) => r.data);

export const saveNavAccessPolicy = (roles) =>
  api.put('/settings/nav-access/policy', { roles }).then((r) => r.data);
