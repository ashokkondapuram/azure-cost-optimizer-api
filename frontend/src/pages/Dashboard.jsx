import React from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { AppCtx } from '../App';
import { fetchDashboardOverview } from '../api/azure';
import PageHeader from '../components/PageHeader';
import PrintExportButton from '../components/PrintExportButton';
import DashboardPortal from '../components/dashboard/DashboardPortal';
import DashboardHero from '../components/dashboard/DashboardHero';
import DashboardOptimizationTrends from '../components/dashboard/DashboardOptimizationTrends';
import DashboardPeriodFilter from '../components/dashboard/DashboardPeriodFilter';
import useDashboardCostPeriod from '../hooks/useDashboardCostPeriod';
import useDashboardSections from '../hooks/useDashboardSections';
import { dashboardCostPeriodLabel } from '../utils/costTimespanUtils';
import { PAGE_ICONS } from '../config/assetIcons';
import {
  SubscriptionRequired, QueryErrorState,
} from '../components/QueryStates';

export default function Dashboard() {
  const { subscription, billingCurrency, subscriptionOptions } = React.useContext(AppCtx);
  const [costPeriod, onCostPeriodChange] = useDashboardCostPeriod();
  const {
    isExpanded,
    toggleSection,
    expandAll,
    collapseAll,
  } = useDashboardSections();

  const {
    data: overview,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ['dashboard-overview', subscription, costPeriod],
    queryFn: () => fetchDashboardOverview({
      subscription_id: subscription,
      timeframe: costPeriod,
    }),
    enabled: !!subscription,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });

  const showInitialSkeleton = isLoading && !overview;

  const currency = billingCurrency || overview?.cost?.summary?.billing_currency || 'CAD';
  const subLabel = subscriptionOptions.find((s) => s.subscriptionId === subscription)?.displayName;
  const periodLabel = dashboardCostPeriodLabel(costPeriod);

  return (
    <div className="page-shell dashboard-page">
      <PageHeader
        title="Dashboard"
        iconKey={PAGE_ICONS.dashboard}
      >
        {subscription && (
          <div className="dashboard-toolbar">
            <DashboardPeriodFilter value={costPeriod} onChange={onCostPeriodChange} />
            <div className="dashboard-section-controls">
              <button type="button" className="btn btn-secondary btn-sm" onClick={expandAll}>
                Expand all
              </button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={collapseAll}>
                Collapse all
              </button>
            </div>
            <PrintExportButton />
          </div>
        )}
      </PageHeader>

      {!subscription && (
        <SubscriptionRequired message="Select a subscription." />
      )}

      {subscription && isError && (
        <QueryErrorState
          error={error}
          onRetry={refetch}
          title="Could not load dashboard"
        />
      )}

      {subscription && !isError && (
        <div className="dashboard-layout">
          <DashboardHero
            subscriptionLabel={subLabel}
            portal={overview?.portal}
            costSummary={overview?.cost?.summary}
            ytdSummary={overview?.cost?.ytd}
            optimizationSummary={overview?.optimization?.summary}
            budgets={overview?.budgets}
            currency={currency}
            isLoading={showInitialSkeleton}
            costPeriodLabel={periodLabel}
          />

          <DashboardOptimizationTrends />

          <DashboardPortal
            portal={overview?.portal}
            currency={currency}
            optimization={overview?.optimization}
            analysisRuns={overview?.analysis_runs}
            topSpendItems={overview?.cost?.top_spend?.items}
            underutilItems={overview?.optimization?.underutil?.items}
            budgets={overview?.budgets}
            dailyPoints={overview?.cost?.daily?.points}
            isLoading={showInitialSkeleton}
            costPeriodLabel={periodLabel}
            isExpanded={isExpanded}
            onToggleSection={toggleSection}
          />
        </div>
      )}
    </div>
  );
}
