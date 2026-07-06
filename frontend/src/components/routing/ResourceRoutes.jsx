import React from 'react';
import { Route, Navigate } from 'react-router-dom';
import ResourceList from '../../pages/ResourceList';
import VirtualMachines from '../../pages/VirtualMachines';
import AKSClusters from '../../pages/AKSClusters';
import { RESOURCE_PAGES, PAGE_ICON_KEYS } from '../../config/appRegistry';
import { LEGACY_RESOURCE_ROUTE_REDIRECTS } from '../../config/resourcePageCatalog';

const PAGE_COMPONENTS = {
  ResourceList,
  VirtualMachines,
  AKSClusters,
};

/** Route elements for App.js — must be direct children of <Routes>, not wrapped in a component. */
export function createResourceRoutes() {
  return [
    ...Object.values(RESOURCE_PAGES).map((page) => {
      const Component = PAGE_COMPONENTS[page.component || 'ResourceList'];
      if (page.component === 'ResourceList') {
        return (
          <Route
            key={page.id}
            path={page.path}
            element={(
              <ResourceList
                title={page.title}
                apiPath={page.apiPath}
                iconKey={PAGE_ICON_KEYS[page.iconKey]}
              />
            )}
          />
        );
      }
      return (
        <Route key={page.id} path={page.path} element={<Component />} />
      );
    }),
    ...Object.entries(LEGACY_RESOURCE_ROUTE_REDIRECTS).map(([from, to]) => (
      <Route key={`legacy-${from}`} path={from} element={<Navigate to={to} replace />} />
    )),
    // NOTE: /findings redirect lives in App.js to avoid duplication
  ];
}
