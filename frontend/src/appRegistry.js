/**
 * appRegistry.js — single source of truth for navigation, page titles,
 * and sidebar group membership.
 *
 * Consumers:
 *   SidebarNav.jsx   — reads NAV_GROUPS + all nav item arrays
 *   App.js           — route paths (kept in sync manually here)
 */

// ── Core nav (always visible) ────────────────────────────────────────────
export const CORE_NAV = [
  { path: '/',                 title: 'Overview' },
];

// ── Advanced tools group ────────────────────────────────────────────
export const ADVANCED_TOOLS_NAV = [
  { path: '/advisor',          title: 'Waste Heatmap' },
  { path: '/tag-compliance',   title: 'Tag Compliance' },
  { path: '/auto-scheduler',   title: 'Auto Scheduler' },
  { path: '/notifications',    title: 'Notification Channels' },
  { path: '/anomaly-detector', title: 'Cost Anomaly Detector' },
  { path: '/timeline',         title: 'Optimization Timeline' },
  { path: '/ai-analysis',      title: 'AI Analysis' },
];

export const ADVANCED_NAV_GROUP = {
  id: 'advanced',
  label: 'Advanced tools',
  color: 'indigo',
  defaultOpen: false,
};

// ── Optimization group ────────────────────────────────────────────────
export const OPTIMIZATION_NAV = [
  { path: '/reservation-advisor', title: 'Reservation Advisor' },
  { path: '/governance',          title: 'Governance' },
  { path: '/cost-allocation',     title: 'Cost Allocation' },
  { path: '/export-center',       title: 'Export Center' },
  { path: '/demand-forecaster',   title: 'Demand Forecaster' },
];

export const OPTIMIZATION_NAV_GROUP = {
  id: 'optimization',
  label: 'Optimization',
  color: 'teal',
  defaultOpen: false,
};

// ── Default open state for all collapsible groups ───────────────────────
export const DEFAULT_NAV_OPEN = {
  advanced: false,
  optimization: false,
};

// ── Path helpers ───────────────────────────────────────────────────────
const _ADVANCED_PATHS = new Set(ADVANCED_TOOLS_NAV.map((n) => n.path));
const _OPTIMIZATION_PATHS = new Set(OPTIMIZATION_NAV.map((n) => n.path));

export function isAdvancedPath(path) { return _ADVANCED_PATHS.has(path); }
export function isOptimizationPath(path) { return _OPTIMIZATION_PATHS.has(path); }

export function groupForPath(path) {
  if (isAdvancedPath(path)) return 'advanced';
  if (isOptimizationPath(path)) return 'optimization';
  return null;
}

const _ALL_PAGES = [
  ...CORE_NAV,
  ...ADVANCED_TOOLS_NAV,
  ...OPTIMIZATION_NAV,
];

export function getPageTitle(path) {
  return _ALL_PAGES.find((p) => p.path === path)?.title ?? 'Azure Cost Optimizer';
}
