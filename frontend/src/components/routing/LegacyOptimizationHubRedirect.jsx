import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { legacyOptimizationHubRedirect } from '../../utils/nestedRoutes';

/** Sends old Optimization hub URLs to Action centre workflow or resources. */
export default function LegacyOptimizationHubRedirect() {
  const location = useLocation();
  const target = legacyOptimizationHubRedirect(location.pathname, location.search);
  return <Navigate to={target} replace />;
}
