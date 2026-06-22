import axios from 'axios';

const BASE_URL = process.env.REACT_APP_API_URL || '';

const api = axios.create({ baseURL: BASE_URL });

export const fetchCosts = (subscriptionId, timeframe = 'MonthToDate', granularity = 'Daily') =>
  api.get('/costs', { params: { subscription_id: subscriptionId, timeframe, granularity } });

export const fetchCostHistory = () => api.get('/costs/history');

export const fetchAllResources = (subscriptionId) =>
  api.get('/resources/all', { params: { subscription_id: subscriptionId } });

export const fetchVMs = (subscriptionId) =>
  api.get('/resources/vms', { params: { subscription_id: subscriptionId } });

export const fetchAKS = (subscriptionId) =>
  api.get('/resources/aks', { params: { subscription_id: subscriptionId } });

export const fetchStorage = (subscriptionId) =>
  api.get('/resources/storage', { params: { subscription_id: subscriptionId } });

export const fetchAppServices = (subscriptionId) =>
  api.get('/resources/appservices', { params: { subscription_id: subscriptionId } });

export const fetchSQL = (subscriptionId) =>
  api.get('/resources/sql', { params: { subscription_id: subscriptionId } });

export const fetchDisks = (subscriptionId) =>
  api.get('/resources/disks', { params: { subscription_id: subscriptionId } });

export const fetchKeyVaults = (subscriptionId) =>
  api.get('/resources/keyvaults', { params: { subscription_id: subscriptionId } });

export const fetchPublicIPs = (subscriptionId) =>
  api.get('/resources/publicips', { params: { subscription_id: subscriptionId } });

export const fetchK8sUtilization = () => api.get('/k8s/utilization');
