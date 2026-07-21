import api from './client';
import { setStoredToken } from './tokenStorage';
import { notifyTokenRefreshed } from '../config/session';
import { withTimeout } from '../utils/apiTimeout';

export { getStoredToken, setStoredToken, getTokenExpiryMs, isTokenExpired, hasActiveSession, getTokenClaims, userFromStoredToken } from './tokenStorage';

const AUTH_ME_TIMEOUT_MS = 15_000;

export function login(credentials) {
  return api.post('/auth/login', credentials).then((r) => r.data);
}

export function fetchCurrentUser() {
  return withTimeout(
    api.get('/auth/me').then((r) => r.data),
    AUTH_ME_TIMEOUT_MS,
    'Session check timed out',
  );
}

export function refreshSession() {
  return api.post('/auth/refresh').then((r) => {
    if (r.data?.access_token) {
      setStoredToken(r.data.access_token);
      notifyTokenRefreshed();
    }
    return r.data;
  });
}

export function fetchUsers() {
  return api.get('/auth/users').then((r) => r.data);
}

export function createUser(body) {
  return api.post('/auth/users', body).then((r) => r.data);
}

export function resetUserPassword(userId, password) {
  return api.patch(`/auth/users/${userId}/password`, { password }).then((r) => r.data);
}

export function applyLoginResult(data) {
  setStoredToken(data.access_token);
  return data.user;
}
