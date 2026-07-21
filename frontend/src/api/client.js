import axios from 'axios';
import { getErrorMessage } from './errors';
import { assertActiveSession, handleUnauthorized, isAuthBootstrapInProgress } from './authSession';
import { getStoredToken } from './tokenStorage';

const api = axios.create({
  baseURL: '/api',
  timeout: Number(process.env.REACT_APP_API_TIMEOUT_MS) || 120_000,
  headers: { 'Content-Type': 'application/json' },
});

function isLoginRequest(url = '') {
  return String(url).includes('/auth/login');
}

api.interceptors.request.use((config) => {
  if (!isLoginRequest(config.url)) {
    try {
      assertActiveSession();
    } catch (err) {
      return Promise.reject(err);
    }
  }

  const token = getStoredToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    error.normalizedMessage = getErrorMessage(error);

    const status = error.response?.status;
    const url = error.config?.url || '';

    if (status === 401 && !isLoginRequest(url) && !isAuthBootstrapInProgress()) {
      handleUnauthorized('api_401');
    }

    return Promise.reject(error);
  },
);

export default api;
