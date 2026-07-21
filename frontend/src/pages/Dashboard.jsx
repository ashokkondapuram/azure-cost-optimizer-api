import React, { useMemo } from 'react';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { AppCtx } from '../App';
import { fetchDashboardOverview, fetchOptimizationTrends } from '../api/azure';
import DashboardPageHead from '../components/dashboard/DashboardPageHead';
import DashboardCostRow from '../components/dashboard/DashboardCostRow';
import DashboardFindingsSummary from '../components/dashboard/DashboardFindingsSummary';
import DashboardBreakdown from '../components/dashboard/DashboardBreakdown';
import DashboardTopOpportunities from '../components/dashboard/DashboardTopOpportunities';
import useDashboardCostPeriod from '../hooks/useDashboardCostPeriod';
import { dashboardCostPeriodLabel } from '../utils/costTimespanUtils';
import { resolveDashboardBillingCurrency, resolveDashboardMtdAmount } from '../utils/costCurrency';
import {
  hasDashboardOverviewData,
  normalizeDashboardOverview,
  resolveDashboardMetrics,
  savingsPctOfMtd,
} from '../utils/dashboardV2Utils';
import {
  SubscriptionRequired, QueryErrorState, EmptyState,
} from '../components/QueryStates';
import { PAGE_ICONS } from '../config/assetIcons';

export default function Dashboard() {
  const { subscription, billingCurrency } = React.useContext(AppCtx);
  const [costPeriod, , costPeriodOptions] = useDashboardCostPeriod();

  const {
    data: overviewRaw,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['dashboard-overview', subscription, costPeriod],
    queryFn: () => fetchDashboardOverview({
      subscription_id: subscription,
      timeframe: costPeriod,
    }),
    enabled: !!subscription,
    staleTime: 120_000,
    gcTime: 300_000,
    retry: 1,
    placeholderData: keepPreviousData,
  });

  const { data: trends } = useQuery({
    queryKey: ['optimization-trends', subscription],
    queryFn: () => fetchOptimizationTrends({ subscription_id: subscription }),
    enabled: Boolean(subscription),
    staleTime: 120_000,
    placeholderData: keepPreviousData,
  });

  const overview = useMemo(
    () => normalizeDashboardOverview(overviewRaw),
    [overviewRaw],
  );

  const showInitialSkeleton = (isLoading || isFetching) && !overview;
  const hasDashboardData = hasDashboardOverviewData(overview);
  const showSyncEmptyHint = !showInitialSkeleton && !isError && overview && !hasDashboardData;

  const currency = billingCurrency || resolveDashboardBillingCurrency(
    overview?.cost?.summary,
    overview?.sync?.cost,
    'CAD',
  );
  const periodLabel = dashboardCostPeriodLabel(costPeriod, costPeriodOptions);

  const metrics = useMemo(
    () => resolveDashboardMetrics({
      summary: overview?.optimization?.summary,
      portal: overview?.portal,
      costSummary: overview?.cost?.summary,
      currency,
      trends,
    }),
    [overview, currency, trends],
  );

  const analysisAt = overview?.sync?.analysis?.last_job_at
    || overview?.analysis_runs?.[0]?.analyzed_at
    || null;

  const costSummary = overview?.cost?.summary;
  const mtdAmount = resolveDashboardMtdAmount(costSummary, overview?.sync?.cost);
  const savingsPct = savingsPctOfMtd(metrics.estSavings, mtdAmount);

  if (!subscription) {
    return (
      <div className="dashboard-v2">
        <SubscriptionRequired message="Select a subscription." />
      </div>
    );
  }

  if (isError && !overview) {
    return (
      <div className="dashboard-v2">
        <QueryErrorState
          error={error}
          onRetry={refetch}
          title="Could not load dashboard"
        />
      </div>
    );
  }

  return (
    <section className="dashboard-v2" aria-label="Dashboard">
      <DashboardPageHead
        periodLabel={periodLabel}
        analysisAt={analysisAt}
        onExport={() => window.print()}
      />

      {isError && overview && (
        <div className="panel" role="alert" style={{ marginBottom: 16 }}>
          <QueryErrorState
            error={error}
            onRetry={refetch}
            title="Some dashboard data could not be refreshed"
          />
        </div>
      )}

      {showSyncEmptyHint && (
        <EmptyState
          iconKey={PAGE_ICONS.dashboard}
          message="Dashboard data is empty for this subscription. Sync resources and costs, then refresh."
        />
      )}

      {!showInitialSkeleton && hasDashboardData && (
        <>
          <DashboardCostRow
            currency={currency}
            spendLabel={periodLabel}
            mtdAmount={mtdAmount}
            periodStart={costSummary?.period_start || costSummary?.mtd_start}
            periodEnd={costSummary?.period_end || costSummary?.mtd_end}
            projectedMonthly={metrics.projectedMonthly}
            mtdDelta={metrics.mtdDelta}
            weeklyAvg={metrics.weeklyAvg}
            potentialSavings={metrics.estSavings}
            savingsPct={savingsPct}
            dailyPoints={overview?.cost?.daily?.points}
          />

          <DashboardFindingsSummary
            summary={overview?.optimization?.summary}
            metrics={metrics}
          />

          <DashboardBreakdown summary={overview?.optimization?.summary} />

          <DashboardTopOpportunities
            recommendations={overview?.optimization?.recommendations}
            currency={currency}
          />
        </>
      )}

      {showInitialSkeleton && (
        <div className="panel" aria-busy="true" style={{ minHeight: 240 }} />
      )}
    </section>
  );
}
