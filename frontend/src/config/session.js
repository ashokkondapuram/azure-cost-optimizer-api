/** Client inactivity timeout before sign-out (default 1 minute). */
export const SESSION_IDLE_MS = Number(process.env.REACT_APP_SESSION_IDLE_MS) || 60_000;

/** Throttle token refresh calls while the user is active. */
export const SESSION_REFRESH_THROTTLE_MS = 30_000;

export const AUTH_TOKEN_REFRESHED_EVENT = 'auth:token-refreshed';

export function notifyTokenRefreshed() {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new Event(AUTH_TOKEN_REFRESHED_EVENT));
}
