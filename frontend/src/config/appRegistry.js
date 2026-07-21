/**
 * Single source of truth for navigation, routes, dashboard tiles, and page metadata.
 * Add a resource here once — sidebar, routes, and dashboard stay in sync.
 */

import { PAGE_ICON_KEYS, NAV_GROUP_KEYS } from './azureIconRegistry';
import { apiPathForCountKey } from './resourceApiPaths';
import { syncTypesForApiPath } from '../utils/syncScope';
import { buildPerTypeResourcePages } from './resourcePageCatalog';

/** Product name shown in sidebar, login, and browser title. */
export const APP_NAME = 'InfinityOps';
export const APP_TAGLINE = 'Cost and optimization for Azure';

/** Login page copy (internal tool) */
export const LOGIN_HERO_TITLE = 'Subscription overview and optimization';
export const LOGIN_HERO_DESC =
  'Track spend, billed resources, open findings, and estimated savings—the same signals on your dashboard after sign-in.';
/** Generic login hover copy — rotates on each interaction (not product-feature specific). */
export const LOGIN_OPTIMIZATION_REVEALS = [
  {
    eyebrow: 'Subscription overview',
    headline: 'Spend, forecast, and savings in one place',
    bullets: [
      'Month-to-date and year-to-date spend at a glance',
      'Forecast month and weekly cost trends',
      'Jump to Action centre from open findings',
    ],
  },
  {
    eyebrow: 'Action centre',
    headline: 'Prioritize what to fix first',
    bullets: [
      'Open findings with estimated monthly savings',
      'Billed resources linked to findings',
      'Proposed actions ready for review',
    ],
  },
  {
    eyebrow: 'Health & advisor',
    headline: 'Spot risk before it becomes spend',
    bullets: [
      'Resources with warnings or critical signals',
      'Azure Advisor findings in context',
      'Top spend and underutilization on the dashboard',
    ],
  },
];
/** @deprecated Use LOGIN_OPTIMIZATION_REVEALS */
export const LOGIN_OPTIMIZATION_REVEAL = LOGIN_OPTIMIZATION_REVEALS[0];
/** @deprecated Use LOGIN_OPTIMIZATION_REVEALS */
export const LOGIN_OPTIMIZATION_HINT = LOGIN_OPTIMIZATION_REVEALS[0].headline;
export const LOGIN_CARD_SUBTITLE = 'Sign in to continue.';
export const LOGIN_FEATURES = [
  { id: 'overview', label: 'Dashboard', desc: 'Spend, forecast, and subscription KPIs' },
  { id: 'action', label: 'Action centre', desc: 'Open findings and estimated savings' },
  { id: 'health', label: 'Health & advisor', desc: 'Resource health and Advisor signals' },
];

/** Demo preview panels on the login page — labels match dashboard KPIs. */
export const LOGIN_FEATURE_PREVIEWS = {
  overview: {
    eyebrow: 'Subscription overview',
    metric: '$124,580',
    metricLabel: 'Spend this period',
    detail: 'Month to date · synced billing',
    rows: [
      { label: 'Year to date', value: '$892,400', tone: 'sky' },
      { label: 'Forecast month', value: '$138,200', tone: 'violet' },
      { label: 'Weekly cost', value: '$31,450', tone: 'amber' },
    ],
    chips: ['↓ 8% vs prior period'],
  },
  action: {
    eyebrow: 'Action centre',
    metric: '47',
    metricLabel: 'Open findings',
    detail: 'Review findings and proposed actions',
    rows: [
      { label: 'Est. savings/mo', value: '$18,240', tone: 'teal' },
      { label: 'Billed resources', value: '2,847', tone: 'sky' },
      { label: 'Critical / high', value: '12', tone: 'amber' },
    ],
  },
  health: {
    eyebrow: 'Health & advisor',
    metric: '2,847',
    metricLabel: 'Billed resources',
    detail: 'Synced inventory with utilization signals',
    rows: [
      { label: 'Resources with warnings', value: '23', tone: 'amber' },
      { label: 'Advisor findings', value: '8', tone: 'violet' },
      { label: 'Critical resources', value: '4', tone: 'rose' },
    ],
  },
};

/** @typedef {'ResourceList' | 'DiskInventoryPage' | 'VirtualMachines' | 'AKSClusters'} PageComponent */

/**
 * @typedef {Object} ResourcePageDef
 * @property {string} id
 * @property {string} path
 * @property {string} title
 * @property {string} navLabel
 * @property {string} apiPath
 * @property {string} [countKey]
 * @property {string} iconKey
 * @property {PageComponent} [component]
 * @property {string} navGroup
 * @property {string} dashboardSection
 * @property {boolean} [alwaysShowOnDashboard]
 */

/**
 * @typedef {Object} NavGroupDef
 * @property {string} id
 * @property {string} label
 * @property {string} iconKey
 * @property {string} color
 * @property {boolean} [defaultOpen]
 * @property {string[]} resourceIds
 */

/**
 * @typedef {Object} DashboardSectionDef
 * @property {string} id
 * @property {string} label
 * @property {string} [description]
 * @property {string} color
 * @property {string} iconKey
 * @property {Array<{ type: 'page', path: string, title: string, iconKey: string, countKey?: string, alwaysShow?: boolean } | { type: 'resource', id: string }>} items
 */

/** @type {Record<string, ResourcePageDef>} */
export const RESOURCE_PAGES = {
  vms: {
    id: 'vms',
    path: '/vms',
    title: 'Virtual machines',
    navLabel: 'Virtual machines',
    apiPath: '/resources/vms',
    countKey: 'vms',
    iconKey: 'vms',
    component: 'VirtualMachines',
    navGroup: 'compute',
    dashboardSection: 'compute',
  },
  disks: {
    id: 'disks',
    path: '/disks',
    title: 'Managed disks',
    navLabel: 'Managed disks',
    apiPath: '/resources/disks',
    countKey: 'disks',
    iconKey: 'disks',
    component: 'DiskInventoryPage',
    navGroup: 'storage',
    dashboardSection: 'storage',
  },
  snapshots: {
    id: 'snapshots',
    path: '/snapshots',
    title: 'Disk snapshots',
    navLabel: 'Disk snapshots',
    apiPath: '/resources/snapshots',
    countKey: 'snapshots',
    iconKey: 'snapshots',
    component: 'ResourceList',
    navGroup: 'storage',
    dashboardSection: 'storage',
  },
  aks: {
    id: 'aks',
    path: '/aks',
    title: 'AKS clusters',
    navLabel: 'AKS clusters',
    apiPath: '/resources/aks',
    countKey: 'aks',
    iconKey: 'aks',
    component: 'AKSClusters',
    navGroup: 'containers',
    dashboardSection: 'compute',
  },
  acr: {
    id: 'acr',
    path: '/acr',
    title: 'Container registries',
    navLabel: 'Container registries',
    apiPath: '/resources/acr',
    countKey: 'acr',
    iconKey: 'acr',
    component: 'ResourceList',
    navGroup: 'containers',
    dashboardSection: 'compute',
  },
  appservices: {
    id: 'appservices',
    path: '/appservices',
    title: 'Web / function apps',
    navLabel: 'Web / function apps',
    apiPath: '/resources/appservices',
    countKey: 'appservices',
    iconKey: 'appservices',
    component: 'ResourceList',
    navGroup: 'appservices',
    dashboardSection: 'apps',
  },
  appserviceplans: {
    id: 'appserviceplans',
    path: '/appserviceplans',
    title: 'App Service plans',
    navLabel: 'App Service plans',
    apiPath: '/resources/appserviceplans',
    countKey: 'appserviceplans',
    iconKey: 'appserviceplans',
    component: 'ResourceList',
    navGroup: 'appservices',
    dashboardSection: 'apps',
  },
  storage: {
    id: 'storage',
    path: '/storage',
    title: 'Storage accounts',
    navLabel: 'Storage accounts',
    apiPath: '/resources/storage',
    countKey: 'storage',
    iconKey: 'storage',
    component: 'ResourceList',
    navGroup: 'storage',
    dashboardSection: 'storage',
  },
  publicips: {
    id: 'publicips',
    path: '/publicips',
    title: 'Public IPs',
    navLabel: 'Public IPs',
    apiPath: '/resources/publicips',
    countKey: 'publicips',
    iconKey: 'publicips',
    component: 'ResourceList',
    navGroup: 'networking',
    dashboardSection: 'network',
  },
  vnets: {
    id: 'vnets',
    path: '/vnets',
    title: 'Virtual networks',
    navLabel: 'Virtual networks',
    apiPath: '/resources/vnets',
    countKey: 'vnets',
    iconKey: 'vnets',
    component: 'ResourceList',
    navGroup: 'networking',
    dashboardSection: 'network',
  },
  nics: {
    id: 'nics',
    path: '/nics',
    title: 'Network interfaces',
    navLabel: 'Network interfaces',
    apiPath: '/resources/nics',
    countKey: 'nics',
    iconKey: 'nics',
    component: 'ResourceList',
    navGroup: 'networking',
    dashboardSection: 'network',
  },
  natgateways: {
    id: 'natgateways',
    path: '/natgateways',
    title: 'NAT gateways',
    navLabel: 'NAT gateways',
    apiPath: '/resources/natgateways',
    countKey: 'natgateways',
    iconKey: 'natgateways',
    component: 'ResourceList',
    navGroup: 'networking',
    dashboardSection: 'network',
  },
  loadbalancers: {
    id: 'loadbalancers',
    path: '/loadbalancers',
    title: 'Load balancers',
    navLabel: 'Load balancers',
    apiPath: '/resources/loadbalancers',
    countKey: 'loadbalancers',
    iconKey: 'loadbalancers',
    component: 'ResourceList',
    navGroup: 'networking',
    dashboardSection: 'network',
  },
  appgateways: {
    id: 'appgateways',
    path: '/appgateways',
    title: 'Application gateways',
    navLabel: 'App gateways',
    apiPath: '/resources/appgateways',
    countKey: 'appgateways',
    iconKey: 'appgateways',
    component: 'ResourceList',
    navGroup: 'networking',
    dashboardSection: 'network',
  },
  nsgs: {
    id: 'nsgs',
    path: '/nsgs',
    title: 'Network security groups',
    navLabel: 'Network security groups',
    apiPath: '/resources/nsgs',
    countKey: 'nsgs',
    iconKey: 'nsgs',
    component: 'ResourceList',
    navGroup: 'networking',
    dashboardSection: 'network',
  },
  privateendpoints: {
    id: 'privateendpoints',
    path: '/privateendpoints',
    title: 'Private endpoints',
    navLabel: 'Private endpoints',
    apiPath: '/resources/privateendpoints',
    countKey: 'privateendpoints',
    iconKey: 'privateendpoints',
    component: 'ResourceList',
    navGroup: 'networking',
    dashboardSection: 'network',
  },
  privatelinkservices: {
    id: 'privatelinkservices',
    path: '/privatelinkservices',
    title: 'Private link services',
    navLabel: 'Private link services',
    apiPath: '/resources/privatelinkservices',
    countKey: 'privatelinkservices',
    iconKey: 'privatelinkservices',
    component: 'ResourceList',
    navGroup: 'networking',
    dashboardSection: 'network',
  },
  privatedns: {
    id: 'privatedns',
    path: '/privatedns',
    title: 'Private DNS zones',
    navLabel: 'Private DNS zones',
    apiPath: '/resources/privatedns',
    countKey: 'privatedns',
    iconKey: 'privatedns',
    component: 'ResourceList',
    navGroup: 'networking',
    dashboardSection: 'network',
  },
  sql: {
    id: 'sql',
    path: '/sql',
    title: 'SQL servers',
    navLabel: 'SQL servers',
    apiPath: '/resources/sql',
    countKey: 'sql',
    iconKey: 'sql',
    component: 'ResourceList',
    navGroup: 'databases',
    dashboardSection: 'data',
  },
  cosmosdb: {
    id: 'cosmosdb',
    path: '/cosmosdb',
    title: 'Cosmos DB',
    navLabel: 'Cosmos DB',
    apiPath: '/resources/cosmosdb',
    countKey: 'cosmosdb',
    iconKey: 'cosmosdb',
    component: 'ResourceList',
    navGroup: 'databases',
    dashboardSection: 'data',
  },
  postgresql: {
    id: 'postgresql',
    path: '/postgresql',
    title: 'PostgreSQL',
    navLabel: 'PostgreSQL',
    apiPath: '/resources/postgresql',
    countKey: 'postgresql',
    iconKey: 'postgresql',
    component: 'ResourceList',
    navGroup: 'databases',
    dashboardSection: 'data',
  },
  redis: {
    id: 'redis',
    path: '/redis',
    title: 'Redis cache',
    navLabel: 'Redis cache',
    apiPath: '/resources/redis',
    countKey: 'redis',
    iconKey: 'redis',
    component: 'ResourceList',
    navGroup: 'databases',
    dashboardSection: 'data',
  },
  ...buildPerTypeResourcePages(),
  keyvaults: {
    id: 'keyvaults',
    path: '/keyvaults',
    title: 'Key vaults',
    navLabel: 'Key vaults',
    apiPath: '/resources/keyvaults',
    countKey: 'keyvaults',
    iconKey: 'keyvaults',
    component: 'ResourceList',
    navGroup: 'security',
    dashboardSection: 'security',
  },
  'cost-resources': {
    id: 'cost-resources',
    path: '/cost-resources',
    title: 'Resources with MTD cost',
    navLabel: 'Resources with cost',
    apiPath: '/resources/from-cost',
    countKey: 'cost_resources',
    iconKey: 'costResources',
    component: 'ResourceList',
    navGroup: 'overview',
    dashboardSection: 'overview',
    alwaysShowOnDashboard: false,
    hidden: true,
  },
};

// Align list API paths with canonical enrichment table routes.
for (const page of Object.values(RESOURCE_PAGES)) {
  if (page.countKey && page.id !== 'cost-resources') {
    const path = apiPathForCountKey(page.countKey);
    if (path) page.apiPath = path;
  }
}

/** Resource catalog for sync, dashboard, and deep links — not shown as sidebar tabs. */
export const RESOURCE_NAV_CATALOG = [
  { id: 'compute', label: 'Compute', iconKey: 'compute', color: '#60a5fa', defaultOpen: true, resourceIds: ['vms'] },
  { id: 'containers', label: 'Containers', iconKey: 'containers', color: '#a78bfa', resourceIds: ['aks', 'acr'] },
  { id: 'appservices', label: 'App services', iconKey: 'appservices', color: '#22d3ee', resourceIds: ['appservices', 'appserviceplans'] },
  { id: 'storage', label: 'Storage', iconKey: 'storage', color: '#fbbf24', defaultOpen: true, resourceIds: ['disks', 'snapshots', 'storage'] },
  { id: 'networking', label: 'Networking', iconKey: 'networking', color: '#34d399', resourceIds: ['publicips', 'vnets', 'nics', 'natgateways', 'loadbalancers', 'appgateways', 'nsgs', 'privateendpoints', 'privatelinkservices', 'privatedns'] },
  { id: 'databases', label: 'Databases', iconKey: 'databases', color: '#f87171', resourceIds: ['sql', 'cosmosdb', 'postgresql', 'redis'] },
  { id: 'monitoring', label: 'Monitoring', iconKey: 'monitoring', color: '#a78bfa', resourceIds: ['loganalytics', 'appinsights'] },
  { id: 'integration', label: 'Integration', iconKey: 'integration', color: '#2dd4bf', resourceIds: ['apim', 'datafactory', 'logicapps'] },
  { id: 'messaging', label: 'Messaging', iconKey: 'messaging', color: '#facc15', resourceIds: ['eventhubs', 'servicebus'] },
  { id: 'analytics', label: 'Analytics', iconKey: 'analytics', color: '#c084fc', resourceIds: ['databricks', 'synapse', 'adx', 'mlworkspace'] },
  { id: 'backup', label: 'Backup', iconKey: 'backup', color: '#94a3b8', resourceIds: ['recoveryvault'] },
  { id: 'search', label: 'Search', iconKey: 'search', color: '#818cf8', resourceIds: ['cognitivesearch'] },
  { id: 'security', label: 'Security', iconKey: 'security', color: '#fb923c', resourceIds: ['keyvaults'] },
];

/** Sidebar resource groups — empty when using unified Action centre. */
export const NAV_RESOURCE_GROUPS = [];

export const OVERVIEW_NAV = [
  { path: '/dashboard', title: 'Dashboard', iconKey: 'dashboard', end: true },
  { path: '/action-centre', title: 'Action centre', iconKey: 'actionCentre' },
  { path: '/explorer', title: 'Resource inventory', iconKey: 'cloudExplorer', superuserOnly: true },
  { path: '/costs', title: 'Cost explorer', iconKey: 'costs' },
];

/** Short nav link hints shown on hover (Concept v2 sidebar). */
export const NAV_LINK_HINTS = {
  '/dashboard': 'Overview and findings',
  '/action-centre': 'Review and approve savings',
  '/costs': 'Spend trends and anomalies',
  '/explorer': 'Inventory and metrics',
  '/settings': 'Thresholds and integrations',
  '/admin/api-explorer': 'API routes and live context',
  '/admin/optimization': 'Sync and analysis jobs',
  '/history': 'Past analysis runs',
  '/activity-log': 'Audit and activity events',
  '/waste-heatmap': 'Idle resources by category',
  '/anomaly-detector': 'Unusual spend spikes',
  '/demand-forecaster': 'Spend forecast trends',
  '/cost-comparison': 'Period-over-period spend',
  '/savings-planner': 'Savings plans and RI modeling',
  '/reservation-advisor': 'Reservations and commitments',
  '/budgets': 'Budget thresholds and alerts',
  '/quota-usage': 'Regional quota utilization',
  '/planned-maintenance': 'Azure maintenance events',
};

/** Deep link into Action centre for a resource type tile or legacy inventory route. */
export function actionCentreTypeLink(resourcePageId, { search, resource } = {}) {
  const params = new URLSearchParams();
  if (resourcePageId) params.set('resourceType', resourcePageId);
  if (resource) {
    const rid = String(resource).trim();
    if (rid) params.set('resource', rid.startsWith('/') ? rid : `/${rid}`);
  }
  if (search) params.set('search', search);
  const qs = params.toString();
  return `/action-centre${qs ? `?${qs}` : ''}`;
}

/**
 * Advanced tools sidebar groups (between Overview and Resources).
 * Each item maps directly to a lazy-loaded route in App.js.
 */
export const ADVANCED_NAV_GROUPS = [
  {
    id: 'advanced-insights',
    label: 'Cost insights',
    iconKey: 'insights',
    color: '#f97316',
    defaultOpen: true,
    items: [
      { path: '/waste-heatmap', title: 'Waste heatmap', iconKey: 'wasteHeatmap' },
      { path: '/anomaly-detector', title: 'Anomaly detector', iconKey: 'anomalyDetector' },
      { path: '/demand-forecaster', title: 'Demand forecaster', iconKey: 'demandForecaster' },
      { path: '/cost-comparison', title: 'Cost comparison', iconKey: 'costs' },
    ],
  },
  {
    id: 'advanced-savings',
    label: 'Savings & budgets',
    iconKey: 'savings',
    color: '#22c55e',
    defaultOpen: false,
    items: [
      { path: '/savings-planner', title: 'Savings planner', iconKey: 'savingsPlanner' },
      { path: '/reservation-advisor', title: 'Reservation advisor', iconKey: 'reservationAdvisor' },
      { path: '/budgets', title: 'Budget manager', iconKey: 'budgetsNav' },
    ],
  },
  {
    id: 'advanced-operations',
    label: 'Operations',
    iconKey: 'operations',
    color: '#8b5cf6',
    defaultOpen: false,
    items: [
      { path: '/planned-maintenance', title: 'Planned maintenance', iconKey: 'plannedMaintenance' },
      { path: '/quota-usage', title: 'Quota usage', iconKey: 'quotaUsage' },
    ],
  },
];

/** Flat list of advanced tool routes (nav access, command palette, titles). */
export const ADVANCED_TOOLS_NAV = ADVANCED_NAV_GROUPS.flatMap((group) => group.items);

/** Collapsible sidebar group for optimization tools and admin settings. */
export const SYSTEM_NAV_GROUP = {
  id: 'system',
  label: 'System',
  iconKey: 'settings',
  color: '#64748b',
  defaultOpen: false,
  adminOnly: true,
};

/** @deprecated Legacy single-group id; use ADVANCED_NAV_GROUPS. */
export const ADVANCED_NAV_GROUP = {
  id: 'advanced',
  label: 'Advanced tools',
  iconKey: 'optimization',
  color: '#818cf8',
  defaultOpen: false,
};

/** @deprecated Use SYSTEM_NAV_GROUP */
export const OPTIMIZATION_NAV_GROUP = SYSTEM_NAV_GROUP;

/**
 * @typedef {Object} OptimizationNavItem
 * @property {string} path
 * @property {string} title
 * @property {string} iconKey
 * @property {string} [section] — subgroup label inside the nav group
 * @property {boolean} [adminOnly]
 */

/** @type {OptimizationNavItem[]} */
export const OPTIMIZATION_NAV_ITEMS = [
  {
    path: '/admin/optimization',
    title: 'Sync center',
    iconKey: 'optimization',
    section: 'Operations',
    adminOnly: true,
  },
  {
    path: '/history',
    title: 'Run history',
    iconKey: 'history',
    section: 'Operations',
  },
  {
    path: '/activity-log',
    title: 'Activity log',
    iconKey: 'history',
    section: 'Operations',
  },
];

/** Extra nav links shown under a resource category. */
export const NAV_GROUP_EXTRA_LINKS = {};

/** @deprecated Use OPTIMIZATION_NAV_ITEMS */
export const ENGINE_NAV = OPTIMIZATION_NAV_ITEMS;

export const SYSTEM_NAV = [
  {
    path: '/settings',
    title: 'Settings',
    iconKey: 'settings',
    section: 'Administration',
    adminOnly: true,
  },
  {
    path: '/admin/api-explorer',
    title: 'API explorer',
    iconKey: 'apiExplorer',
    section: 'Administration',
    adminOnly: true,
  },
];

/** Path → sidebar/page iconKey for overview, advanced, optimization, and system routes. */
export const PATH_ICON_KEYS = Object.fromEntries([
  ...OVERVIEW_NAV,
  ...ADVANCED_TOOLS_NAV,
  ...OPTIMIZATION_NAV_ITEMS,
  ...SYSTEM_NAV,
].map((item) => [item.path, item.iconKey]));

/** Resolve the page icon key alias for a nav route path. */
export function iconKeyForPath(path) {
  return PATH_ICON_KEYS[path] || null;
}

/** @type {DashboardSectionDef[]} */
export const DASHBOARD_SECTIONS = [
  {
    id: 'overview',
    label: 'Cost & optimization',
    color: '#6366f1',
    iconKey: 'costs',
    items: [
      { type: 'page', path: '/dashboard', title: 'Dashboard', iconKey: 'dashboard', alwaysShow: true },
      { type: 'page', path: '/action-centre', title: 'Action centre', iconKey: 'actionCentre', alwaysShow: true },
      { type: 'page', path: '/explorer', title: 'Resource inventory', iconKey: 'cloudExplorer', superuserOnly: true },
      { type: 'page', path: '/costs', title: 'Cost explorer', iconKey: 'costs', alwaysShow: true },
    ],
  },
  {
    id: 'compute',
    label: 'Compute & containers',
    color: '#3b82f6',
    iconKey: 'vms',
    items: [
      { type: 'resource', id: 'vms' },
      { type: 'resource', id: 'aks' },
      { type: 'resource', id: 'acr' },
      { type: 'page', path: '/k8s', title: 'Cluster utilization', iconKey: 'kubernetes', alwaysShow: true },
    ],
  },
  {
    id: 'apps',
    label: 'Apps',
    color: '#0891b2',
    iconKey: 'appservices',
    items: [
      { type: 'resource', id: 'appservices' },
      { type: 'resource', id: 'appserviceplans' },
    ],
  },
  {
    id: 'storage',
    label: 'Storage',
    color: '#fbbf24',
    iconKey: 'storage',
    items: [
      { type: 'resource', id: 'disks' },
      { type: 'resource', id: 'snapshots' },
      { type: 'resource', id: 'storage' },
    ],
  },
  {
    id: 'network',
    label: 'Networking',
    color: '#059669',
    iconKey: 'publicips',
    items: [
      { type: 'resource', id: 'publicips' },
      { type: 'resource', id: 'vnets' },
      { type: 'resource', id: 'nics' },
      { type: 'resource', id: 'natgateways' },
      { type: 'resource', id: 'loadbalancers' },
      { type: 'resource', id: 'appgateways' },
      { type: 'resource', id: 'nsgs' },
      { type: 'resource', id: 'privateendpoints' },
      { type: 'resource', id: 'privatelinkservices' },
      { type: 'resource', id: 'privatedns' },
    ],
  },
  {
    id: 'data',
    label: 'Databases',
    color: '#dc2626',
    iconKey: 'sql',
    items: [
      { type: 'resource', id: 'sql' },
      { type: 'resource', id: 'cosmosdb' },
      { type: 'resource', id: 'postgresql' },
      { type: 'resource', id: 'redis' },
    ],
  },
  {
    id: 'platform',
    label: 'Platform services',
    color: '#7c3aed',
    iconKey: 'monitoring',
    items: [
      { type: 'resource', id: 'loganalytics' },
      { type: 'resource', id: 'appinsights' },
      { type: 'resource', id: 'apim' },
      { type: 'resource', id: 'datafactory' },
      { type: 'resource', id: 'logicapps' },
      { type: 'resource', id: 'eventhubs' },
      { type: 'resource', id: 'servicebus' },
      { type: 'resource', id: 'databricks' },
      { type: 'resource', id: 'synapse' },
      { type: 'resource', id: 'adx' },
      { type: 'resource', id: 'mlworkspace' },
    ],
  },
  {
    id: 'security',
    label: 'Security & backup',
    color: '#64748b',
    iconKey: 'keyvaults',
    items: [
      { type: 'resource', id: 'keyvaults' },
      { type: 'resource', id: 'recoveryvault' },
      { type: 'resource', id: 'cognitivesearch' },
    ],
  },
];

// ── Derived helpers ───────────────────────────────────────────────────────────

export const NAV_GROUPS = Object.fromEntries(
  NAV_RESOURCE_GROUPS.map((g) => [g.id, { label: g.label, routes: g.resourceIds.map((id) => RESOURCE_PAGES[id].path) }]),
);

/** Master collapsible section wrapping all advanced tool groups. */
export const ADVANCED_SECTION_ID = 'advanced-section';

export const DEFAULT_NAV_OPEN = {
  ...Object.fromEntries(
    NAV_RESOURCE_GROUPS.map((g) => [g.id, !!g.defaultOpen]),
  ),
  ...Object.fromEntries(
    ADVANCED_NAV_GROUPS.map((g) => [g.id, !!g.defaultOpen]),
  ),
  [ADVANCED_SECTION_ID]: true,
  [SYSTEM_NAV_GROUP.id]: SYSTEM_NAV_GROUP.defaultOpen,
};

const OPTIMIZATION_PATHS = OPTIMIZATION_NAV_ITEMS.map((item) => item.path);
const SYSTEM_PATHS = SYSTEM_NAV.map((item) => item.path);
const ADVANCED_PATHS = ADVANCED_TOOLS_NAV.map((item) => item.path);

export function isOptimizationPath(pathname) {
  return OPTIMIZATION_PATHS.some(
    (p) => pathname === p || pathname.startsWith(`${p}/`),
  );
}

export function isSystemPath(pathname) {
  return isOptimizationPath(pathname)
    || SYSTEM_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export function isAdvancedPath(pathname) {
  return ADVANCED_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/** System nav (optimization tools + admin) is admin-only in the sidebar. */
export function isSystemNavVisible(isAdmin) {
  return Boolean(isAdmin);
}

export function systemNavItems(isAdmin) {
  if (!isSystemNavVisible(isAdmin)) return [];
  return [
    ...OPTIMIZATION_NAV_ITEMS,
    ...SYSTEM_NAV,
  ].filter((item) => !item.adminOnly || isAdmin);
}

/** Resolve persisted open state (migrates legacy `optimization` key). */
export function systemNavGroupOpen(groups) {
  if (groups?.[SYSTEM_NAV_GROUP.id] != null) return !!groups[SYSTEM_NAV_GROUP.id];
  if (groups?.optimization != null) return !!groups.optimization;
  return !!SYSTEM_NAV_GROUP.defaultOpen;
}

/** Resolve persisted open state for an advanced nav subgroup (migrates legacy `advanced` key). */
export function advancedNavGroupOpen(groups, groupId) {
  if (groups?.[groupId] != null) return !!groups[groupId];
  if (groups?.advanced != null) return !!groups.advanced;
  const group = ADVANCED_NAV_GROUPS.find((g) => g.id === groupId);
  return !!group?.defaultOpen;
}

/** Whether the Advanced section (all tool groups) is expanded in the sidebar. */
export function advancedNavSectionOpen(groups) {
  if (groups?.[ADVANCED_SECTION_ID] != null) return !!groups[ADVANCED_SECTION_ID];
  return true;
}

export function groupForPath(pathname) {
  if (isSystemPath(pathname)) return SYSTEM_NAV_GROUP.id;
  const advancedGroup = ADVANCED_NAV_GROUPS.find((group) =>
    group.items.some((item) => pathname === item.path || pathname.startsWith(`${item.path}/`)),
  );
  if (advancedGroup) return advancedGroup.id;
  return Object.entries(NAV_GROUPS).find(([, g]) =>
    g.routes.some((r) => pathname === r || pathname.startsWith(`${r}/`)),
  )?.[0] ?? null;
}


export function getPageTitle(pathname) {
  if (pathname.startsWith('/explorer')) {
    return 'Resource inventory';
  }
  if (pathname.startsWith('/action-centre')) {
    if (pathname.includes('/workflow')) {
      return 'Action centre · Workflow';
    }
    return 'Action centre';
  }
  if (pathname.startsWith('/resource/')) {
    return 'Resource analysis';
  }
  if (pathname === '/dashboard') {
    return 'Dashboard';
  }

  const extra = {
    '/dashboard': 'Dashboard',
    '/action-centre': 'Action centre',
    '/explorer': 'Resource inventory',
    '/costs': 'Cost explorer',
    '/admin/api-explorer': 'API explorer',
    // Phase 1 advanced
    '/waste-heatmap':    'Waste heatmap',
    '/planned-maintenance': 'Planned maintenance',
    '/quota-usage': 'Quota usage',
    '/anomaly-detector': 'Anomaly detector',
    '/budgets':          'Budget manager',
    '/savings-planner':  'Savings planner',
    '/reservation-advisor': 'Reservation advisor',
    '/cost-comparison':  'Cost comparison',
    '/activity-log':     'Activity log',
    '/demand-forecaster': 'Demand forecaster',
  };
  if (extra[pathname]) return extra[pathname];
  const resource = Object.values(RESOURCE_PAGES).find((p) => p.path === pathname);
  if (resource) return resource.title;
  const overview = [...OVERVIEW_NAV, ...OPTIMIZATION_NAV_ITEMS, ...SYSTEM_NAV, ...ADVANCED_TOOLS_NAV].find((p) => p.path === pathname);
  return overview?.title || APP_NAME;
}

export function resolveDashboardItem(item) {
  if (item.type === 'page') {
    return {
      name: item.title,
      link: item.path,
      iconKey: item.iconKey,
      countKey: item.countKey,
      alwaysShow: item.alwaysShow,
    };
  }
  const page = RESOURCE_PAGES[item.id];
  if (!page) return null;
  return {
    name: page.title,
    link: actionCentreTypeLink(page.id),
    iconKey: page.iconKey,
    countKey: page.countKey,
    alwaysShow: page.alwaysShowOnDashboard,
  };
}

export function visibleDashboardItems(section, counts) {
  return section.items
    .map(resolveDashboardItem)
    .filter(Boolean)
    .filter((item) => isResourceVisibleOnDashboard(item, counts));
}

/** True when synced inventory exists in the database for this count key. */
export function hasResourceInventory(counts, countKey) {
  if (!countKey) return true;
  return (counts?.[countKey] ?? 0) > 0;
}

/** True when type has MTD spend or open analysis findings. */
export function hasResourceCost(counts, countKey) {
  if (!countKey) return true;
  const row = counts?.breakdown?.[countKey];
  if (row && typeof row.has_cost === 'boolean') return row.has_cost;
  if (!row) return false;
  return Number(row?.cost_mtd ?? 0) > 0 || Number(row?.findings_count ?? 0) > 0;
}

/** Dashboard tiles: only resource types with MTD cost (free types hidden). */
export function isResourceVisibleOnDashboard(pageOrItem, counts) {
  if (!pageOrItem) return false;
  if (pageOrItem.hidden) return false;
  if (pageOrItem.alwaysShowOnDashboard) return true;
  if (!pageOrItem.countKey) return true;
  return hasResourceCost(counts, pageOrItem.countKey);
}

/** Sidebar nav: show types with MTD cost or analysis findings. */
export function isResourceVisibleInNav(pageOrItem, counts) {
  if (!pageOrItem) return false;
  if (pageOrItem.hidden) return false;
  if (pageOrItem.alwaysShow) return true;
  if (!pageOrItem.countKey) return true;
  if (counts?.breakdown) {
    return hasResourceCost(counts, pageOrItem.countKey);
  }
  return hasResourceInventory(counts, pageOrItem.countKey);
}

/** @deprecated Use isResourceVisibleInNav or isResourceVisibleOnDashboard */
export function isResourceVisibleInUi(pageOrItem, counts) {
  return isResourceVisibleInNav(pageOrItem, counts);
}

/** Total synced resources across all pages in a nav group. */
export function categoryResourceCount(group, counts, { costOnly = false } = {}) {
  let total = 0;
  for (const resourceId of group?.resourceIds || []) {
    const page = RESOURCE_PAGES[resourceId];
    if (!page?.countKey) continue;
    if (costOnly && !hasResourceCost(counts, page.countKey)) continue;
    total += counts?.[page.countKey] ?? 0;
  }
  return total;
}

/** Nav groups with child resources filtered to those present in the database. */
export function visibleNavGroups(counts) {
  return NAV_RESOURCE_GROUPS.map((group) => ({
    ...group,
    resourceIds: visibleResourceIdsInGroup(group, counts),
  }));
}

/** Resource page ids in a nav group that have synced inventory. */
export function visibleResourceIdsInGroup(group, counts) {
  return (group?.resourceIds || []).filter((id) => isResourceVisibleInNav(RESOURCE_PAGES[id], counts));
}

/** Canonical sync types for explicit resource page ids (visible nav items). */
export function syncTypesForResourceIds(resourceIds) {
  const types = new Set();
  for (const id of resourceIds || []) {
    const page = RESOURCE_PAGES[id];
    if (!page?.apiPath) continue;
    syncTypesForApiPath(page.apiPath).forEach((t) => types.add(t));
  }
  return [...types];
}

/** Canonical sync types for every resource page in a nav group. */
export function syncTypesForNavGroup(groupId) {
  const group = RESOURCE_NAV_CATALOG.find((g) => g.id === groupId);
  if (!group) return [];
  const types = new Set();
  for (const resourceId of group.resourceIds) {
    const page = RESOURCE_PAGES[resourceId];
    if (!page?.apiPath) continue;
    syncTypesForApiPath(page.apiPath).forEach((t) => types.add(t));
  }
  return [...types];
}

/** Canonical sync types for visible dashboard tiles in a section. */
export function syncTypesForDashboardItems(items, counts) {
  const types = new Set();
  for (const item of items || []) {
    if (item.countKey && !hasResourceCost(counts, item.countKey)) continue;
    const page = Object.values(RESOURCE_PAGES).find((p) => p.path === item.link);
    if (page?.apiPath) {
      syncTypesForApiPath(page.apiPath).forEach((t) => types.add(t));
      continue;
    }
    if (item.countKey) {
      const pageByKey = Object.values(RESOURCE_PAGES).find((p) => p.countKey === item.countKey);
      if (pageByKey?.apiPath) {
        syncTypesForApiPath(pageByKey.apiPath).forEach((t) => types.add(t));
      }
    }
  }
  return [...types];
}

/** Canonical sync types for a dashboard section's resource tiles. */
export function syncTypesForDashboardSection(section, counts = null) {
  const types = new Set();
  for (const item of section?.items || []) {
    if (item.type !== 'resource') continue;
    const page = RESOURCE_PAGES[item.id];
    if (!page?.apiPath) continue;
    syncTypesForApiPath(page.apiPath).forEach((t) => types.add(t));
  }
  return [...types];
}

export function formatDashboardCount(counts, _breakdown, countKey) {
  if (!countKey) return null;
  const row = counts?.breakdown?.[countKey];
  const total = row?.has_cost === false ? 0 : (counts?.[countKey] ?? 0);
  return { total, hint: null };
}

/** Validate registry integrity (used in tests). */
export function validateAppRegistry() {
  const errors = [];
  for (const group of RESOURCE_NAV_CATALOG) {
    for (const id of group.resourceIds) {
      if (!RESOURCE_PAGES[id]) errors.push(`Nav group "${group.id}" references unknown resource "${id}"`);
      else if (RESOURCE_PAGES[id].navGroup !== group.id) {
        errors.push(`Resource "${id}" navGroup mismatch`);
      }
    }
    if (!NAV_GROUP_KEYS[group.iconKey]) errors.push(`Nav group "${group.id}" missing icon key`);
  }
  for (const [id, page] of Object.entries(RESOURCE_PAGES)) {
    if (!PAGE_ICON_KEYS[page.iconKey]) errors.push(`Resource "${id}" missing page icon`);
    if (page.component === 'ResourceList' && !page.apiPath) errors.push(`Resource "${id}" missing apiPath`);
  }
  for (const section of DASHBOARD_SECTIONS) {
    for (const item of section.items) {
      if (item.type === 'resource' && !RESOURCE_PAGES[item.id]) {
        errors.push(`Dashboard section "${section.id}" references unknown resource "${item.id}"`);
      }
      if (item.iconKey && !PAGE_ICON_KEYS[item.iconKey]) {
        errors.push(`Dashboard item "${item.path || item.id}" missing page icon`);
      }
    }
    if (section.iconKey && !PAGE_ICON_KEYS[section.iconKey]) {
      errors.push(`Dashboard section "${section.id}" missing icon key`);
    }
  }
  for (const nav of [...OVERVIEW_NAV, ...ADVANCED_TOOLS_NAV, ...OPTIMIZATION_NAV_ITEMS, ...SYSTEM_NAV]) {
    if (!PAGE_ICON_KEYS[nav.iconKey]) errors.push(`Nav "${nav.path}" missing page icon`);
  }
  for (const group of ADVANCED_NAV_GROUPS) {
    if (!NAV_GROUP_KEYS[group.iconKey]) errors.push(`Advanced nav group "${group.id}" missing icon key`);
  }
  return errors;
}

// Re-export icon maps for nav components
export { PAGE_ICON_KEYS, NAV_GROUP_KEYS };
