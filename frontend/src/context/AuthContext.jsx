import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import {
  fetchCurrentUser,
  hasActiveSession,
  login as apiLogin,
  setStoredToken,
  userFromStoredToken,
} from '../api/auth';
import { getStoredToken, getTokenExpiryMs } from '../api/tokenStorage';
import { handleUnauthorized, setAuthBootstrapInProgress } from '../api/authSession';

const TOKEN_KEY = 'finops_auth_token';
const SESSION_CHECK_MS = 30_000;

const AuthCtx = createContext({
  user: null,
  loading: true,
  isAuthenticated: false,
  isAdmin: false,
  login: async () => {},
  logout: () => {},
  refreshUser: async () => {},
});

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sessionTick, setSessionTick] = useState(0);

  const logout = useCallback(() => {
    setStoredToken(null);
    setUser(null);
  }, []);

  const hydrateUserFromToken = useCallback(() => {
    const cached = userFromStoredToken();
    if (cached) {
      setUser((prev) => prev ?? {
        id: cached.id,
        username: cached.username,
        display_name: cached.display_name,
        role: cached.role,
      });
    }
    return cached;
  }, []);

  const loadUser = useCallback(async () => {
    setAuthBootstrapInProgress(true);
    if (!hasActiveSession()) {
      logout();
      setAuthBootstrapInProgress(false);
      setLoading(false);
      return;
    }

    hydrateUserFromToken();

    try {
      const me = await fetchCurrentUser();
      setUser(me);
    } catch (err) {
      const status = err?.response?.status;
      if (status === 401 || err?.code === 'SESSION_EXPIRED') {
        handleUnauthorized('auth_me_failed');
      }
      // Keep JWT-backed session on transient errors; user stays signed in until token expires.
    } finally {
      setAuthBootstrapInProgress(false);
      setLoading(false);
    }
  }, [logout, hydrateUserFromToken]);

  useEffect(() => {
    loadUser();
  }, [loadUser]);

  useEffect(() => {
    const bump = () => setSessionTick((value) => value + 1);

    const onStorage = (event) => {
      if (event.key === TOKEN_KEY) bump();
    };
    window.addEventListener('storage', onStorage);

    const token = getStoredToken();
    const expMs = token ? getTokenExpiryMs(token) : null;
    let expiryTimer;
    if (expMs) {
      expiryTimer = setTimeout(bump, Math.max(expMs - Date.now(), 0) + 500);
    }

    const pollId = setInterval(bump, SESSION_CHECK_MS);

    return () => {
      window.removeEventListener('storage', onStorage);
      clearInterval(pollId);
      if (expiryTimer) clearTimeout(expiryTimer);
    };
  }, [user]);

  useEffect(() => {
    if (loading) return;
    if (!hasActiveSession() && user) {
      logout();
    }
  }, [loading, user, sessionTick, logout]);

  const login = useCallback(async (username, password) => {
    const data = await apiLogin({ username, password });
    setStoredToken(data.access_token);
    setUser(data.user);
    setSessionTick((value) => value + 1);
    return data.user;
  }, []);

  const sessionActive = hasActiveSession();

  const value = useMemo(() => ({
    user,
    loading,
    isAuthenticated: sessionActive && (!!user || !!userFromStoredToken()),
    isAdmin: user?.role === 'admin',
    login,
    logout,
    refreshUser: loadUser,
  }), [user, loading, login, logout, loadUser, sessionActive, sessionTick]);

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth() {
  return useContext(AuthCtx);
}

export default AuthCtx;
