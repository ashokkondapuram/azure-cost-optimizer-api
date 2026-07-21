const TOKEN_KEY = 'finops_auth_token';

export function getStoredToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

function decodeTokenPayload(token) {
  try {
    const segment = token.split('.')[1];
    if (!segment) return null;
    const normalized = segment.replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(normalized));
  } catch {
    return null;
  }
}

export function getTokenExpiryMs(token) {
  const payload = decodeTokenPayload(token);
  if (!payload?.exp) return null;
  return payload.exp * 1000;
}

export function isTokenExpired(token, skewMs = 30_000) {
  if (!token) return true;
  const expMs = getTokenExpiryMs(token);
  if (!expMs) return false;
  return Date.now() >= expMs - skewMs;
}

export function getTokenClaims(token = getStoredToken()) {
  if (!token) return null;
  const payload = decodeTokenPayload(token);
  if (!payload?.sub || !payload?.username) return null;
  return {
    id: payload.sub,
    username: payload.username,
    role: payload.role || 'viewer',
    display_name: payload.username,
    is_admin: payload.role === 'admin',
  };
}

export function userFromStoredToken() {
  return getTokenClaims();
}

export function hasActiveSession() {
  const token = getStoredToken();
  return !!token && !isTokenExpired(token);
}
