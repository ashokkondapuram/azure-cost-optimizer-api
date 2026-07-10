import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
} from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AppCtx } from '../App';
import { fetchOptimizationTrends } from '../api/azure';

const VALID_TABS = new Set([
  'overview',
  'actions',
  'scoreboard',
]);

/** Legacy deep links from removed or renamed hub tabs. */
const LEGACY_TAB_ALIASES = {
  recommendations: 'actions',
  advisor: 'actions',
  findings: 'actions',
  rollout: 'overview',
};

const VALID_ACTION_STATUSES = new Set(['proposed', 'approved', 'executed', 'rejected', 'deferred']);

const OptimizationHubCtx = createContext(null);

function resolveTab(rawTab) {
  const normalized = LEGACY_TAB_ALIASES[rawTab] || rawTab || 'overview';
  return VALID_TABS.has(normalized) ? normalized : 'overview';
}

/** Canonical subscription savings — unified engine + Advisor rollup. */
export function resolveHubEstimatedSavings(trends) {
  if (!trends) return 0;
  return trends.unified_estimated_monthly_savings
    ?? trends.total_estimated_monthly_savings
    ?? trends.distinct_estimated_monthly_savings
    ?? 0;
}

/** Distinct savings across all optimization action rows (workflow table; may include stale rows). */
export function resolveActionPipelineSavings(trends) {
  if (!trends) return 0;
  return trends.action_pipeline_savings
    ?? trends.distinct_estimated_monthly_savings
    ?? 0;
}

export function OptimizationHubProvider({ children }) {
  const { subscription } = useContext(AppCtx);
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = resolveTab(searchParams.get('tab'));
  const rawStatus = searchParams.get('status') || '';
  const actionsStatus = VALID_ACTION_STATUSES.has(rawStatus) ? rawStatus : '';

  const trendsQuery = useQuery({
    queryKey: ['optimization-trends', subscription],
    queryFn: () => fetchOptimizationTrends({ subscription_id: subscription }),
    enabled: Boolean(subscription),
    staleTime: 60_000,
  });

  const estimatedMonthlySavings = resolveHubEstimatedSavings(trendsQuery.data);
  const actionPipelineSavings = resolveActionPipelineSavings(trendsQuery.data);

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
    () => ({
      tab,
      setTab,
      actionsStatus,
      setActionsStatus,
      trends: trendsQuery.data,
      trendsLoading: trendsQuery.isLoading,
      estimatedMonthlySavings,
      actionPipelineSavings,
      refreshHubMetrics: trendsQuery.refetch,
    }),
    [
      tab,
      setTab,
      actionsStatus,
      setActionsStatus,
      trendsQuery.data,
      trendsQuery.isLoading,
      estimatedMonthlySavings,
      actionPipelineSavings,
      trendsQuery.refetch,
    ],
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
  { id: 'overview',   label: 'Overview',   iconKey: 'dashboard',   desc: 'Workflow and signals' },
  { id: 'actions',    label: 'Actions',    iconKey: 'actions',     desc: 'Review and approve' },
  { id: 'scoreboard', label: 'Scoreboard', iconKey: 'scoreboard',  desc: 'Resource scoring' },
];
