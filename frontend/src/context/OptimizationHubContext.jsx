import React, { createContext, useCallback, useContext, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

const VALID_TABS = new Set([
  'overview',
  'actions',
  'scoreboard',
]);

/** Legacy deep links from separate Recommendations / Advisor tabs. */
const LEGACY_TAB_ALIASES = {
  recommendations: 'actions',
  advisor: 'actions',
};

const VALID_ACTION_STATUSES = new Set(['proposed', 'approved', 'executed', 'rejected', 'deferred']);

const OptimizationHubCtx = createContext(null);

function resolveTab(rawTab) {
  const normalized = LEGACY_TAB_ALIASES[rawTab] || rawTab || 'overview';
  return VALID_TABS.has(normalized) ? normalized : 'overview';
}

export function OptimizationHubProvider({ children }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = resolveTab(searchParams.get('tab'));
  const rawStatus = searchParams.get('status') || '';
  const actionsStatus = VALID_ACTION_STATUSES.has(rawStatus) ? rawStatus : '';

  const setTab = useCallback((nextTab, { status } = {}) => {
    const resolved = resolveTab(nextTab);
    if (!VALID_TABS.has(resolved)) return;
    const next = new URLSearchParams();
    next.set('tab', resolved);
    if (resolved === 'actions' && status && VALID_ACTION_STATUSES.has(status)) {
      next.set('status', status);
    }
    setSearchParams(next, { replace: true });
  }, [setSearchParams]);

  const setActionsStatus = useCallback((status) => {
    const next = new URLSearchParams(searchParams);
    next.set('tab', 'actions');
    if (status && VALID_ACTION_STATUSES.has(status)) {
      next.set('status', status);
    } else {
      next.delete('status');
    }
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const value = useMemo(
    () => ({ tab, setTab, actionsStatus, setActionsStatus }),
    [tab, setTab, actionsStatus, setActionsStatus],
  );

  return (
    <OptimizationHubCtx.Provider value={value}>
      {children}
    </OptimizationHubCtx.Provider>
  );
}

export function useOptionalOptimizationHub() {
  return useContext(OptimizationHubCtx);
}

export function useOptimizationHub() {
  const ctx = useContext(OptimizationHubCtx);
  if (!ctx) {
    throw new Error('useOptimizationHub must be used within OptimizationHubProvider');
  }
  return ctx;
}

export const OPTIMIZATION_HUB_TABS = [
  { id: 'overview', label: 'Overview', iconKey: 'dashboard', desc: 'Workflow and signals' },
  { id: 'actions', label: 'Actions', iconKey: 'actions', desc: 'Review and approve' },
  { id: 'scoreboard', label: 'Scoreboard', iconKey: 'scoreboard', desc: 'Resource scoring' },
];
