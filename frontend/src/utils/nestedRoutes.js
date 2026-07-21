import { EXPLORER_TABS } from '../context/CloudExplorerContext';

export const EXPLORER_TAB_IDS = new Set(EXPLORER_TABS.map((t) => t.id));

export const HUB_TAB_IDS = new Set(['actions']);

/** @deprecated Workflow tab removed — use resources view with hasAction filter. */
export const ACTION_CENTRE_VIEWS = new Set(['resources', 'workflow']);

const HUB_LEGACY_ALIASES = {
  overview: 'actions',
  recommendations: 'actions',
  advisor: 'actions',
  findings: 'actions',
  scoreboard: 'actions',
  rollout: 'actions',
  'rollout-monitor': 'actions',
};

const LEGACY_HUB_RESOURCE_TABS = new Set(['recommendations', 'advisor', 'findings', 'overview']);

const LEGACY_EXPLORER_ISSUE_TABS = new Set(['issues', 'overview', 'findings', 'recommendations', 'advisor']);

/** Canonical resource inventory path (superuser only). */
export function explorerPath() {
  return '/explorer';
}

/** Action centre path filtered to resources with proposed optimization actions. */
export function actionCentreProposedPath() {
  return '/action-centre?hasAction=1';
}

/** Path for Action centre — default resources list or proposed-actions filter. */
export function actionCentrePath(view = 'resources') {
  if (view === 'workflow') {
    return actionCentreProposedPath();
  }
  return '/action-centre';
}

/** @deprecated Use actionCentreProposedPath() — kept for existing imports. */
export function optimizationHubPath(tab = 'actions') {
  resolveHubTab(tab);
  return actionCentreProposedPath();
}

export function resolveExplorerTab(raw) {
  const tab = (raw || 'inventory').toLowerCase();
  if (LEGACY_EXPLORER_ISSUE_TABS.has(tab)) return 'issues';
  return EXPLORER_TAB_IDS.has(tab) ? tab : 'inventory';
}

export function resolveHubTab(raw) {
  const normalized = HUB_LEGACY_ALIASES[raw] || raw || 'actions';
  return HUB_TAB_IDS.has(normalized) ? normalized : 'actions';
}

/** Parse explorer tab from pathname — non-inventory legacy tabs map to issues redirect. */
export function explorerTabFromPath(pathname = '') {
  const parts = pathname.replace(/\/+$/, '').split('/').filter(Boolean);
  if (parts[0] !== 'explorer') return 'inventory';
  if (parts.length < 2) return 'inventory';
  return resolveExplorerTab(parts[1]);
}

/** Redirect target for legacy `/explorer/*` URLs. */
export function legacyExplorerRedirect(pathname = '') {
  const tab = explorerTabFromPath(pathname);
  if (tab === 'issues') return '/action-centre';
  return explorerPath();
}

/** Parse Action centre view from pathname. */
export function actionCentreViewFromPath(pathname = '') {
  const parts = pathname.replace(/\/+$/, '').split('/').filter(Boolean);
  if (parts[0] !== 'action-centre') return 'resources';
  if (parts[1] === 'workflow') return 'workflow';
  return 'resources';
}

/** Parse hub tab from pathname — legacy hub URLs map to proposed-actions filter. */
export function hubTabFromPath(pathname = '') {
  if (actionCentreViewFromPath(pathname) === 'workflow') return 'actions';
  const parts = pathname.replace(/\/+$/, '').split('/').filter(Boolean);
  if (parts[0] !== 'optimization-hub') return 'actions';
  if (parts.length < 2) return 'actions';
  return resolveHubTab(parts[1]);
}

/** Redirect target for legacy `/optimization-hub` URLs. */
export function legacyOptimizationHubRedirect(pathname = '', search = '') {
  const params = new URLSearchParams(search);
  const legacyTab = params.get('tab');
  if (legacyTab && LEGACY_HUB_RESOURCE_TABS.has(legacyTab)) {
    return '/action-centre';
  }
  return actionCentreProposedPath();
}

export function explorerPageTitle() {
  return 'Resource inventory';
}

export function hubPageTitle() {
  return 'Action centre';
}
