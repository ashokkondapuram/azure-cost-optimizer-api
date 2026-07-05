import React, { Suspense, lazy } from 'react';
import AssetIcon from '../components/AssetIcon';
import { LoadingState } from '../components/QueryStates';
import {
  OptimizationHubProvider,
  useOptimizationHub,
  OPTIMIZATION_HUB_TABS,
} from '../context/OptimizationHubContext';

const OptimizationHubOverview = lazy(() => import('../components/optimization/OptimizationHubOverview'));
const OptimizationActions = lazy(() => import('./OptimizationActions'));
const OptimizationScoreboard = lazy(() => import('./OptimizationScoreboard'));

function OptimizationHubSidebar() {
  const { tab, setTab } = useOptimizationHub();

  return (
    <aside className="optimization-hub-sidebar" aria-label="Optimization hub navigation">
      <div className="optimization-hub-sidebar__brand">
        <AssetIcon iconKey="actions" size={18} alt="" />
        <div>
          <strong>Optimization hub</strong>
          <span>Review · score · save</span>
        </div>
      </div>
      <nav className="optimization-hub-sidebar__nav" role="tablist">
        {OPTIMIZATION_HUB_TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={`optimization-hub-sidebar__tab${tab === item.id ? ' optimization-hub-sidebar__tab--active' : ''}`}
            onClick={() => setTab(item.id)}
          >
            <AssetIcon iconKey={item.iconKey} size={16} alt="" />
            <span className="optimization-hub-sidebar__tab-text">
              <span className="optimization-hub-sidebar__tab-label">{item.label}</span>
              <span className="optimization-hub-sidebar__tab-desc">{item.desc}</span>
            </span>
          </button>
        ))}
      </nav>
    </aside>
  );
}

function OptimizationHubPanel() {
  const { tab } = useOptimizationHub();

  return (
    <Suspense fallback={<LoadingState message="Loading…" />}>
      {tab === 'overview' && <OptimizationHubOverview />}
      {tab === 'actions' && <OptimizationActions embedded />}
      {tab === 'scoreboard' && <OptimizationScoreboard embedded />}
    </Suspense>
  );
}

export default function OptimizationHub() {
  return (
    <OptimizationHubProvider>
      <div className="page-shell optimization-hub-page optimization-hub-page--layout">
        <div className="optimization-hub-layout">
          <OptimizationHubSidebar />
          <div className="optimization-hub-main" role="tabpanel">
            <OptimizationHubPanel />
          </div>
        </div>
      </div>
    </OptimizationHubProvider>
  );
}
