/**
 * Global session-expiry handling for API clients and auth context.
 * Registered from AuthSessionSync (inside React Router).
 */
import { getStoredToken, hasActiveSession, isTokenExpired, setStoredToken } from './tokenStorage';

let unauthorizedHandler = null;
let handlingUnauthorized = false;
let authBootstrapInProgress = true;

export function setAuthBootstrapInProgress(inProgress) {
  authBootstrapInProgress = Boolean(inProgress);
}

export function isAuthBootstrapInProgress() {
  return authBootstrapInProgress;
}

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
}

export function clearUnauthorizedHandler() {
  unauthorizedHandler = null;
}

function buildLoginPath() {
  const next = `${window.location.pathname}${window.location.search}`;
  if (!next || next === '/login') return '/login';
  return `/login?next=${encodeURIComponent(next)}`;
}

/**
 * Clear credentials and redirect to login (SPA navigation when handler is set).
 */
export function handleUnauthorized(reason = 'session_expired') {
  if (handlingUnauthorized) return;
  if (authBootstrapInProgress && reason === 'api_401') {
    return;
  }
  handlingUnauthorized = true;

  const onLoginPage = window.location.pathname === '/login';
  const loginPath = buildLoginPath();

  if (!onLoginPage) {
    setStoredToken(null);
  }

  if (typeof unauthorizedHandler === 'function' && !onLoginPage) {
    try {
      unauthorizedHandler({ reason, loginPath });
    } finally {
      window.setTimeout(() => {
        handlingUnauthorized = false;
        if (!hasActiveSession() && window.location.pathname !== '/login') {
          window.location.assign(loginPath);
        }
      }, 200);
    }
    return;
  }

  if (!onLoginPage) {
    window.location.assign(loginPath);
  }
  handlingUnauthorized = false;
}

/** Reject outgoing requests when the stored JWT is already expired. */
export function assertActiveSession() {
  const token = getStoredToken();
  if (!token) return;
  if (isTokenExpired(token)) {
    handleUnauthorized('token_expired');
    const error = new Error('Session expired');
    error.code = 'SESSION_EXPIRED';
    throw error;
  }
}
