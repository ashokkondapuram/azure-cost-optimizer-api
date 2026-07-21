import { useCallback, useEffect, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../context/AuthContext';
import useIdleSession from '../hooks/useIdleSession';
import {
  clearUnauthorizedHandler,
  setUnauthorizedHandler,
} from '../api/authSession';
import { getStoredToken, getTokenExpiryMs, hasActiveSession } from '../api/tokenStorage';
import { AUTH_TOKEN_REFRESHED_EVENT } from '../config/session';

import { loginPathWithNext } from '../utils/authRedirect';

const SESSION_POLL_MS = 60_000;

function buildLoginPath(pathname, search = '') {
  return loginPathWithNext(pathname, search);
}

/**
 * Keeps auth state in sync with JWT validity and redirects to login when the
 * session ends. Must render inside BrowserRouter.
 */
export default function AuthSessionSync() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const { logout, refreshUser, isAuthenticated, loading } = useAuth();
  const expiryTimerRef = useRef(null);
  const locationRef = useRef(location);

  locationRef.current = location;

  const redirectToLogin = useCallback(() => {
    const { pathname, search } = locationRef.current;
    if (pathname === '/login') return;

    logout();
    queryClient.clear();
    navigate(buildLoginPath(pathname, search), {
      replace: true,
      state: { from: locationRef.current },
    });
  }, [logout, navigate, queryClient]);

  useIdleSession({
    enabled: isAuthenticated && !loading && location.pathname !== '/login',
    onIdle: redirectToLogin,
  });

  useEffect(() => {
    setUnauthorizedHandler(({ loginPath }) => {
      logout();
      queryClient.clear();
      const { pathname } = locationRef.current;
      if (pathname !== '/login') {
        navigate(loginPath || '/login', {
          replace: true,
          state: { from: locationRef.current },
        });
      }
    });
    return () => clearUnauthorizedHandler();
  }, [logout, navigate, queryClient]);

  useEffect(() => {
    if (loading) return undefined;
    if (!hasActiveSession() && location.pathname !== '/login') {
      redirectToLogin();
    }
    return undefined;
  }, [loading, location.pathname, redirectToLogin]);

  const scheduleExpiryCheck = useCallback(() => {
    if (expiryTimerRef.current) {
      clearTimeout(expiryTimerRef.current);
      expiryTimerRef.current = null;
    }

    const token = getStoredToken();
    const expMs = token ? getTokenExpiryMs(token) : null;
    if (!expMs) return;

    const delay = Math.max(expMs - Date.now(), 0);
    expiryTimerRef.current = setTimeout(() => {
      if (!hasActiveSession()) {
        redirectToLogin();
      }
    }, delay + 500);
  }, [redirectToLogin]);

  useEffect(() => {
    if (loading || !isAuthenticated) {
      if (expiryTimerRef.current) clearTimeout(expiryTimerRef.current);
      return undefined;
    }

    scheduleExpiryCheck();

    const pollId = setInterval(() => {
      if (!hasActiveSession()) {
        redirectToLogin();
        return;
      }
      refreshUser().catch(() => {
        /* refreshUser clears invalid sessions */
      });
    }, SESSION_POLL_MS);

    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      if (!hasActiveSession()) {
        redirectToLogin();
        return;
      }
      refreshUser().catch(() => {});
    };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener(AUTH_TOKEN_REFRESHED_EVENT, scheduleExpiryCheck);

    return () => {
      clearInterval(pollId);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener(AUTH_TOKEN_REFRESHED_EVENT, scheduleExpiryCheck);
      if (expiryTimerRef.current) clearTimeout(expiryTimerRef.current);
    };
  }, [isAuthenticated, loading, redirectToLogin, refreshUser, scheduleExpiryCheck]);

  return null;
}
