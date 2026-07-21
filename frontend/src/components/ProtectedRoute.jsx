import React, { useEffect } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { hasActiveSession } from '../api/tokenStorage';
import { LoadingState } from './QueryStates';

import { loginPathWithNext } from '../utils/authRedirect';
import { useNavAccess } from '../hooks/useNavAccess';
import { normalizeNavPath } from '../utils/navAccess';

function loginPathFor(location) {
  return loginPathWithNext(location.pathname, location.search);
}

export default function ProtectedRoute({ children, adminOnly = false, superuserOnly = false, requireNavAccess = true }) {
  const { isAuthenticated, isAdmin, isSuperuser, loading } = useAuth();
  const { canView, loading: navLoading } = useNavAccess();
  const location = useLocation();
  const navigate = useNavigate();
  const sessionActive = hasActiveSession();
  const allowed = isAuthenticated && sessionActive;

  useEffect(() => {
    if (loading || allowed) return;
    if (location.pathname === '/login') return;
    navigate(loginPathFor(location), { replace: true, state: { from: location } });
  }, [loading, allowed, location, navigate]);

  if (loading || (requireNavAccess && navLoading)) {
    return <LoadingState message="Checking session…" />;
  }

  if (!allowed) {
    return <Navigate to={loginPathFor(location)} replace state={{ from: location }} />;
  }

  if (adminOnly && !isAdmin) {
    return <Navigate to="/dashboard" replace />;
  }

  if (superuserOnly && !isSuperuser) {
    return <Navigate to="/dashboard" replace />;
  }

  if (requireNavAccess && !canView(normalizeNavPath(location.pathname))) {
    return <Navigate to="/dashboard" replace />;
  }

  return children;
}
