/**
 * Per-type inventory pages (one Azure service per nav entry).
 * Mirrors app/resource_page_registry.py — keep in sync when adding types.
 */

/** @typedef {import('./appRegistry').ResourcePageDef} ResourcePageDef */

/** @type {Record<string, Omit<ResourcePageDef, 'id": string}>} */
export const PER_TYPE_RESOURCE_PAGES = {
  loganalytics: {
    id: 'loganalytics',
    path: '/loganalytics',
    title: 'Log Analytics workspaces',
    navLabel: 'Log Analytics',
    apiPath: '/resources/loganalytics',
    countKey: 'loganalytics',
    navGroup: 'monitoring',
    dashboardSection: 'platform',
    component: 'ResourceList',
  },
  appinsights: {
    id: 'appinsights',
    path: '/appinsights',
    title: 'Application Insights',
    navLabel: 'Application Insights',
    apiPath: '/resources/appinsights',
    countKey: 'appinsights',
    navGroup: 'monitoring',
    dashboardSection: 'platform',
    component: 'ResourceList',
  },
  apim: {
    id: 'apim',
    path: '/apim',
    title: 'API Management',
    navLabel: 'API Management',
    apiPath: '/resources/apim',
    countKey: 'apim',
    navGroup: 'integration',
    dashboardSection: 'platform',
    component: 'ResourceList',
  },
  datafactory: {
    id: 'datafactory',
    path: '/datafactory',
    title: 'Data factories',
    navLabel: 'Data factories',
    apiPath: '/resources/datafactory',
    countKey: 'datafactory',
    navGroup: 'integration',
    dashboardSection: 'platform',
    component: 'ResourceList',
  },
  logicapps: {
    id: 'logicapps',
    path: '/logicapps',
    title: 'Logic Apps',
    navLabel: 'Logic Apps',
    apiPath: '/resources/logicapps',
    countKey: 'logicapps',
    navGroup: 'integration',
    dashboardSection: 'platform',
    component: 'ResourceList',
  },
  eventhubs: {
    id: 'eventhubs',
    path: '/eventhubs',
    title: 'Event Hubs',
    navLabel: 'Event Hubs',
    apiPath: '/resources/eventhubs',
    countKey: 'eventhubs',
    navGroup: 'messaging',
    dashboardSection: 'platform',
    component: 'ResourceList',
  },
  servicebus: {
    id: 'servicebus',
    path: '/servicebus',
    title: 'Service Bus',
    navLabel: 'Service Bus',
    apiPath: '/resources/servicebus',
    countKey: 'servicebus',
    navGroup: 'messaging',
    dashboardSection: 'platform',
    component: 'ResourceList',
  },
  databricks: {
    id: 'databricks',
    path: '/databricks',
    title: 'Databricks',
    navLabel: 'Databricks',
    apiPath: '/resources/databricks',
    countKey: 'databricks',
    navGroup: 'analytics',
    dashboardSection: 'platform',
    component: 'ResourceList',
  },
  synapse: {
    id: 'synapse',
    path: '/synapse',
    title: 'Synapse Analytics',
    navLabel: 'Synapse Analytics',
    apiPath: '/resources/synapse',
    countKey: 'synapse',
    navGroup: 'analytics',
    dashboardSection: 'platform',
    component: 'ResourceList',
  },
  adx: {
    id: 'adx',
    path: '/adx',
    title: 'Data Explorer',
    navLabel: 'Data Explorer',
    apiPath: '/resources/adx',
    countKey: 'adx',
    navGroup: 'analytics',
    dashboardSection: 'platform',
    component: 'ResourceList',
  },
  mlworkspace: {
    id: 'mlworkspace',
    path: '/mlworkspace',
    title: 'Machine Learning',
    navLabel: 'Machine Learning',
    apiPath: '/resources/mlworkspace',
    countKey: 'mlworkspace',
    navGroup: 'analytics',
    dashboardSection: 'platform',
    component: 'ResourceList',
  },
  recoveryvault: {
    id: 'recoveryvault',
    path: '/recoveryvault',
    title: 'Recovery Services vaults',
    navLabel: 'Recovery vaults',
    apiPath: '/resources/recoveryvault',
    countKey: 'recoveryvault',
    navGroup: 'backup',
    dashboardSection: 'security',
    component: 'ResourceList',
  },
  cognitivesearch: {
    id: 'cognitivesearch',
    path: '/cognitivesearch',
    title: 'AI Search',
    navLabel: 'AI Search',
    apiPath: '/resources/cognitivesearch',
    countKey: 'cognitivesearch',
    navGroup: 'search',
    dashboardSection: 'security',
    component: 'ResourceList',
  },
};

/** Legacy aggregate routes → first child page (for bookmarks). */
export const LEGACY_RESOURCE_ROUTE_REDIRECTS = {
  '/monitoring': '/loganalytics',
  '/integration': '/apim',
  '/messaging': '/eventhubs',
  '/analytics': '/databricks',
  '/backup': '/recoveryvault',
  '/search': '/cognitivesearch',
};

/** Build full page defs with iconKey attached (PAGE_ICON_KEYS entry key == page id). */
export function buildPerTypeResourcePages() {
  return Object.fromEntries(
    Object.entries(PER_TYPE_RESOURCE_PAGES).map(([id, page]) => [
      id,
      { ...page, iconKey: id },
    ]),
  );
}

/** API path → canonical type for scoped sync (mirrors app/resource_page_registry.py). */
export const PER_TYPE_API_PATH_TO_CANONICAL = {
  '/resources/loganalytics': 'monitoring/loganalytics',
  '/resources/appinsights': 'monitoring/appinsights',
  '/resources/apim': 'integration/apim',
  '/resources/datafactory': 'integration/datafactory',
  '/resources/logicapps': 'integration/logicapp',
  '/resources/eventhubs': 'messaging/eventhub',
  '/resources/servicebus': 'messaging/servicebus',
  '/resources/databricks': 'analytics/databricks',
  '/resources/synapse': 'analytics/synapse',
  '/resources/adx': 'analytics/adx',
  '/resources/mlworkspace': 'analytics/mlworkspace',
  '/resources/recoveryvault': 'backup/recoveryvault',
  '/resources/cognitivesearch': 'search/cognitivesearch',
};
