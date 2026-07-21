import React, { lazy, Suspense } from 'react';
import { Route, Navigate, useSearchParams } from 'react-router-dom';
import { RESOURCE_PAGES, PAGE_ICON_KEYS } from '../../config/appRegistry';
import { LEGACY_RESOURCE_ROUTE_REDIRECTS } from '../../config/resourcePageCatalog';
import { normalizeArmResourceId } from '../../utils/armResourceLinks';
import { LoadingState } from '../QueryStates';

const DiskInventoryPage = lazy(() => import('../../disks/DiskInventoryPage'));

const PAGE_COMPONENTS = {
  DiskInventoryPage,
};

function buildActionCentreUrl(page, searchParams) {
  const params = new URLSearchParams();
  if (page?.id) params.set('resourceType', page.id);

  const resourceId = searchParams.get('resourceId') || searchParams.get('resource');
  if (resourceId) {
    params.set('resource', normalizeArmResourceId(resourceId));
  }

  const search = searchParams.get('search');
  if (search) params.set('search', search);

  if (searchParams.get('inspect') === '1') params.set('inspect', '1');
  const section = searchParams.get('section');
  if (section) params.set('section', section);

  const qs = params.toString();
  return `/action-centre${qs ? `?${qs}` : ''}`;
}

function ResourcePageRedirect({ page }) {
  const [searchParams] = useSearchParams();
  return <Navigate to={buildActionCentreUrl(page, searchParams)} replace />;
}

function ResourcePageElement({ page }) {
  const Component = PAGE_COMPONENTS[page.component];
  if (Component) {
    return (
      <Suspense fallback={<LoadingState message="Loading page…" />}>
        <Component />
      </Suspense>
    );
  }
  return <ResourcePageRedirect page={page} />;
}

function LegacyResourceRedirect({ to }) {
  const [searchParams] = useSearchParams();
  const [path, query = ''] = to.split('?');
  const merged = new URLSearchParams(query);
  for (const [key, value] of searchParams.entries()) {
    if (!merged.has(key)) merged.set(key, value);
  }
  const qs = merged.toString();
  return <Navigate to={qs ? `${path}?${qs}` : path} replace />;
}

/** Route elements for App.js — dedicated pages or Action centre redirect. */
export function createResourceRoutes() {
  return [
    ...Object.values(RESOURCE_PAGES).map((page) => (
      <Route
        key={page.id}
        path={page.path}
        element={<ResourcePageElement page={page} />}
      />
    )),
    ...Object.entries(LEGACY_RESOURCE_ROUTE_REDIRECTS).map(([from, to]) => (
      <Route
        key={`legacy-${from}`}
        path={from}
        element={<LegacyResourceRedirect to={to} />}
      />
    )),
  ];
}

/** @deprecated Kept for imports that referenced PAGE_COMPONENTS. */
export { PAGE_COMPONENTS };

/** @deprecated Kept for imports that referenced PAGE_ICON_KEYS re-export pattern. */
export { PAGE_ICON_KEYS };
