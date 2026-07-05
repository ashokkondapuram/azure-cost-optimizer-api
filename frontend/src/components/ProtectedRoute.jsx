import React, { useEffect } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { hasActiveSession } from '../api/tokenStorage';
import { LoadingState } from './QueryStates';

import { loginPathWithNext } from '../utils/authRedirect';

function loginPathFor(location) {
  return loginPathWithNext(location.pathname, location.search);
}

export default function ProtectedRoute({ children, adminOnly = false }) {
  const { isAuthenticated, isAdmin, loading } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const sessionActive = hasActiveSession();
  const allowed = isAuthenticated && sessionActive;

  useEffect(() => {
    if (loading || allowed) return;
    if (location.pathname === '/login') return;
    navigate(loginPathFor(location), { replace: true, state: { from: location } });
  }, [loading, allowed, location, navigate]);

  if (loading) {
    return <LoadingState message="Checking session…" />;
  }

  if (!allowed) {
    return <Navigate to={loginPathFor(location)} replace state={{ from: location }} />;
  }

  if (adminOnly && !isAdmin) {
    return <Navigate to="/" replace />;
  }

  return children;
}
