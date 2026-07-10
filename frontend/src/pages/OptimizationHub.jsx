import React, { Suspense, lazy } from 'react';
import { Link } from 'react-router-dom';
import PageHeader from '../components/PageHeader';
import OptimizationHubTabBar from '../components/optimization/OptimizationHubTabBar';
import { LoadingState } from '../components/QueryStates';
import AdminOnly from '../components/AdminOnly';
import { OptimizationHubProvider, useOptimizationHub } from '../context/OptimizationHubContext';
import { PAGE_ICONS } from '../config/assetIcons';

const OptimizationHubOverview = lazy(() => import('../components/optimization/OptimizationHubOverview'));
const OptimizationActions     = lazy(() => import('./OptimizationActions'));
const OptimizationScoreboard  = lazy(() => import('./OptimizationScoreboard'));

function OptimizationHubPanel() {
  const { tab } = useOptimizationHub();

  return (
    <div
      className="optimization-hub-panel"
      role="tabpanel"
      id={`optimization-hub-panel-${tab}`}
      aria-labelledby={`optimization-hub-tab-${tab}`}
    >
      <Suspense fallback={<LoadingState message="Loading…" />}>
        {tab === 'overview' && <OptimizationHubOverview />}
        {tab === 'actions' && <OptimizationActions embedded />}
        {tab === 'scoreboard' && <OptimizationScoreboard embedded />}
      </Suspense>
    </div>
  );
}

function OptimizationHubPage() {
  return (
    <div className="page-shell optimization-hub-page optimization-hub-page--tabs">
      <PageHeader
        title="Optimization hub"
        subtitle="Review signals, approve actions, and track savings impact"
        iconKey={PAGE_ICONS.optimizationHub}
      >
        <AdminOnly>
          <Link to="/admin/optimization" className="btn btn-secondary btn-sm">
            Sync center
          </Link>
        </AdminOnly>
        <Link to="/waste-heatmap" className="btn btn-secondary btn-sm">
          Waste heatmap
        </Link>
      </PageHeader>

      <OptimizationHubTabBar />
      <OptimizationHubPanel />
    </div>
  );
}

export default function OptimizationHub() {
  return (
    <OptimizationHubProvider>
      <OptimizationHubPage />
    </OptimizationHubProvider>
  );
}
