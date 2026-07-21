import React, { Suspense, lazy, useContext } from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';
import { AppCtx } from '../App';
import WizPageHero from '../components/layout/WizPageHero';
import { LoadingState } from '../components/QueryStates';
import { legacyExplorerRedirect } from '../utils/nestedRoutes';

const WizInventoryPanel = lazy(() => import('../components/wiz/panels/WizInventoryPanel'));

/** Superuser-only billed resource inventory. */
export default function CloudExplorer() {
  const { subscription } = useContext(AppCtx);
  const location = useLocation();
  const currentPath = location.pathname.replace(/\/+$/, '') || '/';
  const redirectTarget = legacyExplorerRedirect(location.pathname);
  if (redirectTarget !== currentPath) {
    return <Navigate to={redirectTarget} replace />;
  }

  return (
    <div className="page-shell wiz-page">
      <WizPageHero
        title="Resource inventory"
        pageKey="resourceInventory"
        actions={(
          <Link to="/action-centre" className="btn btn-primary btn-sm">
            Action centre
          </Link>
        )}
      >
        {!subscription && (
          <p className="text-muted text-sm" style={{ margin: 0 }}>
            Select a subscription to browse inventory.
          </p>
        )}
      </WizPageHero>

      <Suspense fallback={<LoadingState message="Loading inventory…" />}>
        <WizInventoryPanel />
      </Suspense>
    </div>
  );
}
