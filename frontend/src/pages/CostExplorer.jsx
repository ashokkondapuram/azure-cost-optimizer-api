import React, { useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, keepPreviousData } from '@tanstack/react-query';
import { AppCtx } from '../App';
import { useAuth } from '../context/AuthContext';
import {
  fetchCosts,
  fetchCostByService,
  fetchCostByResource,
  fetchCostSummary,
  fetchBudgets,
  fetchForecast,
  fetchDashboardSyncStatus,
} from '../api/azure';
import { fetchCostComparison } from '../api/costs';
import { fetchDailyAnomalies, fetchServiceAnomalies } from '../api/costAnomaly';
import useCostSync from '../hooks/useCostSync';
import useCostTimeframes from '../hooks/useCostTimeframes';
import AdminOnly from '../components/AdminOnly';
import FetchCostsButton from '../components/FetchCostsButton';
import { SubscriptionRequired, QueryErrorState } from '../components/QueryStates';
import {
  buildCostQueryParams,
  costTimeframeLabel,
  previousCustomRange,
} from '../config/costTimeframes';
import { DISPLAY_CURRENCY } from '../utils/costCurrency';
import { textIncludes } from '../utils/filterUtils';
import { exportCostExplorerCsv } from '../utils/costExplorerExport';
import {
  parseCostRows,
  buildDailyPoints,
  buildCompareDailyPoints,
  buildCumulativePoints,
  buildServiceRows,
  aggregateByField,
  buildResourceSpendRows,
  periodDayCount,
  projectedMonthEnd,
  buildMomBars,
  buildYtdMonthlyStacks,
  resolveCompareTimeframe,
  periodLabel,
  hasCostExplorerData,
} from '../utils/costExplorerV2Utils';
import { buildSpendVelocity } from '../utils/ceChartUtils';
import CostExplorerPageHead from '../components/cost-explorer/CostExplorerPageHead';
import CostExplorerTimeFilter from '../components/cost-explorer/CostExplorerTimeFilter';
import CostExplorerHeroGrid from '../components/cost-explorer/CostExplorerHeroGrid';
import CostExplorerBudgetStrip from '../components/cost-explorer/CostExplorerBudgetStrip';
import CostExplorerCommandBar from '../components/cost-explorer/CostExplorerCommandBar';
import CostExplorerTrendPanel from '../components/cost-explorer/CostExplorerTrendPanel';
import CostExplorerComparisonGrid from '../components/cost-explorer/CostExplorerComparisonGrid';
import CostExplorerBreakdown from '../components/cost-explorer/CostExplorerBreakdown';
import CostExplorerAllocation from '../components/cost-explorer/CostExplorerAllocation';
import CostExplorerTopSpend from '../components/cost-explorer/CostExplorerTopSpend';
import CostExplorerAnomalies from '../components/cost-explorer/CostExplorerAnomalies';

export default function CostExplorer() {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const { isAdmin } = useAuth();
  const timeframeOptions = useCostTimeframes();
  const validTimeframes = useMemo(
    () => new Set(timeframeOptions.map((opt) => opt.value)),
    [timeframeOptions],
  );
  const [searchParams] = useSearchParams();
  const urlTimeframe = searchParams.get('timeframe');

  const [timeframe, setTimeframe] = useState(() => (
    urlTimeframe && validTimeframes.has(urlTimeframe) ? urlTimeframe : 'MonthToDate'
  ));
  const [granularity, setGranularity] = useState('Daily');
  const [customFrom, setCustomFrom] = useState('');
  const [customTo, setCustomTo] = useState('');
  const [search, setSearch] = useState('');
  const [serviceFilter, setServiceFilter] = useState('all');
  const [rgFilter, setRgFilter] = useState('all');
  const [tagFilter, setTagFilter] = useState('all');
  const [chipFilter, setChipFilter] = useState('all');
  const [exporting, setExporting] = useState(false);
  const breakdownRef = useRef(null);

  const compareTimeframe = useMemo(
    () => resolveCompareTimeframe(timeframe),
    [timeframe],
  );
  const [compareCustomFrom, setCompareCustomFrom] = useState('');
  const [compareCustomTo, setCompareCustomTo] = useState('');

  useEffect(() => {
    if (timeframe === 'Custom' && customFrom && customTo) {
      const prev = previousCustomRange(customFrom, customTo);
      if (prev) {
        setCompareCustomFrom(prev.from_date);
        setCompareCustomTo(prev.to_date);
      }
    } else {
      setCompareCustomFrom('');
      setCompareCustomTo('');
    }
  }, [timeframe, customFrom, customTo]);

  const rangeParams = useMemo(
    () => buildCostQueryParams({
      subscription_id: subscription,
      timeframe,
      from_date: timeframe === 'Custom' ? customFrom : undefined,
      to_date: timeframe === 'Custom' ? customTo : undefined,
    }),
    [subscription, timeframe, customFrom, customTo],
  );

  const compareParams = useMemo(() => {
    if (timeframe === 'Last7Days' && compareCustomFrom && compareCustomTo) {
      return buildCostQueryParams({
        subscription_id: subscription,
        timeframe: 'Custom',
        from_date: compareCustomFrom,
        to_date: compareCustomTo,
      });
    }
    return buildCostQueryParams({
      subscription_id: subscription,
      timeframe: compareTimeframe,
    });
  }, [subscription, timeframe, compareTimeframe, compareCustomFrom, compareCustomTo]);

  const rangeReady = timeframe !== 'Custom' || (customFrom && customTo);
  const isMtd = timeframe === 'MonthToDate' || timeframe === 'BillingMonthToDate';
  const showYtd = timeframe === 'ThisYear';
  const isPartialPeriod = isMtd || showYtd;

  const { sync, syncing } = useCostSync({
    subscription,
    invalidateKeys: [
      ['costs', subscription],
      ['cost-summary', subscription],
      ['cost-by-svc', subscription],
      ['cost-by-resource', subscription],
      ['cost-comparison', subscription],
      ['ce-budgets', subscription],
      ['ce-anomalies', subscription],
    ],
  });

  const queryBase = [subscription, timeframe, customFrom, customTo, granularity];

  const costQuery = useQuery({
    queryKey: ['costs', ...queryBase],
    queryFn: () => fetchCosts({ ...rangeParams, granularity }),
    enabled: !!subscription && rangeReady,
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  });

  const compareCostQuery = useQuery({
    queryKey: ['costs-compare', subscription, compareParams, granularity],
    queryFn: () => fetchCosts({ ...compareParams, granularity }),
    enabled: !!subscription && rangeReady,
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  });

  const summaryQuery = useQuery({
    queryKey: ['cost-summary', ...queryBase],
    queryFn: () => fetchCostSummary(rangeParams),
    enabled: !!subscription && rangeReady,
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  });

  const svcQuery = useQuery({
    queryKey: ['cost-by-svc', ...queryBase],
    queryFn: () => fetchCostByService(rangeParams),
    enabled: !!subscription && rangeReady,
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  });

  const resourceQuery = useQuery({
    queryKey: ['cost-by-resource', ...queryBase],
    queryFn: () => fetchCostByResource(rangeParams),
    enabled: !!subscription && rangeReady,
    staleTime: 5 * 60_000,
    placeholderData: keepPreviousData,
  });

  const compareResourceQuery = useQuery({
    queryKey: ['cost-by-resource-compare', subscription, compareParams],
    queryFn: () => fetchCostByResource(compareParams),
    enabled: !!subscription && rangeReady,
    staleTime: 5 * 60_000,
  });

  const comparisonQuery = useQuery({
    queryKey: ['cost-comparison', subscription, timeframe, customFrom, customTo, compareTimeframe],
    queryFn: () => fetchCostComparison({
      subscription_id: subscription,
      current_timeframe: timeframe,
      compare_timeframe: compareTimeframe,
      current_from_date: customFrom || undefined,
      current_to_date: customTo || undefined,
    }),
    enabled: !!subscription && rangeReady,
    staleTime: 5 * 60_000,
  });

  const monthlyQuery = useQuery({
    queryKey: ['costs-monthly', subscription, 'Last6Months'],
    queryFn: () => fetchCosts({
      subscription_id: subscription,
      timeframe: 'Last6Months',
      granularity: 'Monthly',
    }),
    enabled: !!subscription,
    staleTime: 10 * 60_000,
  });

  const ytdMonthlyQuery = useQuery({
    queryKey: ['costs-ytd-monthly', subscription],
    queryFn: () => fetchCosts({
      subscription_id: subscription,
      timeframe: 'ThisYear',
      granularity: 'Monthly',
    }),
    enabled: !!subscription && showYtd,
    staleTime: 10 * 60_000,
  });

  const ytdSvcQuery = useQuery({
    queryKey: ['cost-by-svc-ytd', subscription],
    queryFn: () => fetchCostByService({
      subscription_id: subscription,
      timeframe: 'ThisYear',
    }),
    enabled: !!subscription && showYtd,
    staleTime: 10 * 60_000,
  });

  const budgetsQuery = useQuery({
    queryKey: ['ce-budgets', subscription],
    queryFn: () => fetchBudgets({ subscription_id: subscription }),
    enabled: !!subscription,
    staleTime: 10 * 60_000,
  });

  const forecastQuery = useQuery({
    queryKey: ['ce-forecast', subscription, timeframe],
    queryFn: () => fetchForecast({ subscription_id: subscription, timeframe }),
    enabled: !!subscription && isMtd,
    staleTime: 10 * 60_000,
  });

  const syncStatusQuery = useQuery({
    queryKey: ['dashboard-sync-status', subscription],
    queryFn: () => fetchDashboardSyncStatus({ subscription_id: subscription }),
    enabled: !!subscription,
    staleTime: 60_000,
  });

  const dailyAnomalyQuery = useQuery({
    queryKey: ['ce-anomalies-daily', subscription],
    queryFn: () => fetchDailyAnomalies(subscription),
    enabled: !!subscription,
    staleTime: 5 * 60_000,
  });

  const serviceAnomalyQuery = useQuery({
    queryKey: ['ce-anomalies-service', subscription],
    queryFn: () => fetchServiceAnomalies(subscription),
    enabled: !!subscription,
    staleTime: 5 * 60_000,
  });

  const summary = summaryQuery.data;
  const currency = billingCurrency || summary?.billing_currency || DISPLAY_CURRENCY;
  const periodStart = summary?.period_start || summary?.mtd_start;
  const periodEnd = summary?.period_end || summary?.mtd_end;
  const rangeLabelText = periodLabel(timeframe, timeframeOptions, periodStart, periodEnd);
  const periodTitle = costTimeframeLabel(timeframe, timeframeOptions);
  const comparePeriodLabel = costTimeframeLabel(compareTimeframe, timeframeOptions);

  const dailyRows = parseCostRows(costQuery.data?.data);
  const compareDailyRows = parseCostRows(compareCostQuery.data?.data);
  const svcRows = parseCostRows(svcQuery.data);
  const resourceRows = parseCostRows(resourceQuery.data);
  const compareResourceRows = parseCostRows(compareResourceQuery.data);
  const monthlyRows = parseCostRows(monthlyQuery.data?.data);
  const ytdMonthlyRows = parseCostRows(ytdMonthlyQuery.data?.data);

  const dailyPoints = useMemo(
    () => buildDailyPoints(dailyRows, { periodStart, periodEnd }),
    [dailyRows, periodStart, periodEnd],
  );
  const compareDailyPoints = useMemo(
    () => buildDailyPoints(compareDailyRows),
    [compareDailyRows],
  );
  const dailyChart = useMemo(
    () => buildCompareDailyPoints(dailyPoints, compareDailyRows),
    [dailyPoints, compareDailyRows],
  );
  const cumulativeChart = useMemo(
    () => buildCumulativePoints(dailyPoints),
    [dailyPoints],
  );

  const total = summary?.pretax_total ?? dailyPoints.reduce((s, r) => s + r.cost, 0);
  const compareTotal = comparisonQuery.data?.compare_total ?? null;
  const periodDelta = comparisonQuery.data?.delta ?? (compareTotal != null ? total - compareTotal : null);
  const daysElapsed = periodDayCount(periodStart, periodEnd);
  const avgDaily = total > 0 && daysElapsed ? total / daysElapsed : null;
  const projected = projectedMonthEnd(total, daysElapsed, timeframe)
    ?? (forecastQuery.data?.pretax_total || forecastQuery.data?.cost_usd_total || null);

  const serviceChart = useMemo(() => buildServiceRows(svcRows), [svcRows]);
  const rgRows = useMemo(
    () => aggregateByField(resourceRows, 'ResourceGroup', total),
    [resourceRows, total],
  );
  const regionRows = useMemo(
    () => aggregateByField(resourceRows, 'ResourceLocation', total),
    [resourceRows, total],
  );

  const velocity = useMemo(
    () => buildSpendVelocity(dailyPoints),
    [dailyPoints],
  );

  const resourceSpendRows = useMemo(
    () => buildResourceSpendRows(resourceRows, compareResourceRows, total),
    [resourceRows, compareResourceRows, total],
  );

  const services = useMemo(
    () => [...new Set(resourceSpendRows.map((r) => r.service).filter(Boolean))].sort(),
    [resourceSpendRows],
  );
  const resourceGroups = useMemo(
    () => [...new Set(resourceSpendRows.map((r) => r.resourceGroup).filter(Boolean))].sort(),
    [resourceSpendRows],
  );

  const anomalyResourceIds = useMemo(() => {
    const ids = new Set();
    (serviceAnomalyQuery.data?.service_anomalies || []).forEach((a) => {
      if (a.resource_id) ids.add(a.resource_id);
    });
    return ids;
  }, [serviceAnomalyQuery.data]);

  const filteredSpendRows = useMemo(() => {
    let rows = resourceSpendRows;
    if (search) {
      rows = rows.filter((r) => textIncludes(r.name, search) || textIncludes(r.service, search));
    }
    if (serviceFilter !== 'all') {
      rows = rows.filter((r) => r.service === serviceFilter);
    }
    if (rgFilter !== 'all') {
      rows = rows.filter((r) => r.resourceGroup === rgFilter);
    }
    if (tagFilter !== 'all') {
      rows = rows.filter((r) => r.tag === tagFilter);
    }
    if (chipFilter === 'increasing') {
      rows = rows.filter((r) => (r.trendPct ?? 0) > 0);
    } else if (chipFilter === 'anomaly') {
      rows = rows.filter((r) => anomalyResourceIds.has(r.resourceId));
    } else if (chipFilter === 'top10') {
      rows = rows.slice(0, 10);
    }
    return rows;
  }, [resourceSpendRows, search, serviceFilter, rgFilter, tagFilter, chipFilter, anomalyResourceIds]);

  const momBars = useMemo(() => buildMomBars(monthlyRows), [monthlyRows]);
  const ytdStacks = useMemo(() => {
    if (!showYtd) return [];
    const svcMonthly = parseCostRows(ytdSvcQuery.data);
    if (ytdMonthlyRows.length) return buildYtdMonthlyStacks(ytdMonthlyRows);
    return buildYtdMonthlyStacks(svcMonthly);
  }, [showYtd, ytdMonthlyRows, ytdSvcQuery.data]);

  const forecastPoints = useMemo(() => {
    const forecastTotal = Number(forecastQuery.data?.pretax_total || forecastQuery.data?.cost_usd_total || 0);
    if (!forecastTotal || !dailyPoints.length || !periodEnd) return [];
    const last = dailyPoints[dailyPoints.length - 1];
    const endOfMonth = periodEnd.slice(0, 7) === last.date.slice(0, 7)
      ? periodEnd
      : `${last.date.slice(0, 7)}-${new Date(Number(last.date.slice(0, 4)), Number(last.date.slice(5, 7)), 0).getDate()}`;
    const daysLeft = periodDayCount(last.date, endOfMonth);
    if (!daysLeft || daysLeft <= 0) return [];
    const dailyForecast = (forecastTotal - total) / daysLeft;
    const points = [];
    let d = new Date(`${last.date}T00:00:00`);
    for (let i = 0; i < daysLeft; i += 1) {
      d.setDate(d.getDate() + 1);
      const date = d.toISOString().slice(0, 10);
      points.push({ date, dateLabel: date, cost: Math.max(0, dailyForecast) });
    }
    return points;
  }, [forecastQuery.data, dailyPoints, periodEnd, total]);

  const syncRequired = costQuery.data?.sync_required
    || summaryQuery.data?.sync_required
    || summary?.sync_required
    || svcQuery.data?.sync_required;
  const isLoading = (costQuery.isLoading || summaryQuery.isLoading) && !summaryQuery.data;
  const isError = costQuery.isError || summaryQuery.isError;
  const hasData = hasCostExplorerData({
    summary,
    dailyPoints,
    serviceRows: serviceChart,
    resourceRows: resourceSpendRows,
    syncRequired,
  });
  const costSyncAt = syncStatusQuery.data?.cost?.last_synced_at
    || syncStatusQuery.data?.cost?.updated_at;

  const daysRemaining = useMemo(() => {
    if (!periodEnd) return null;
    const end = new Date(`${periodEnd}T00:00:00`);
    const today = new Date();
    return Math.max(0, Math.round((end - today) / 86400000));
  }, [periodEnd]);

  const handleExport = async () => {
    if (!subscription) return;
    setExporting(true);
    try {
      await exportCostExplorerCsv({
        params: rangeParams,
        currency,
        timeframeLabel: periodTitle,
      });
    } finally {
      setExporting(false);
    }
  };

  const handleRetry = () => {
    costQuery.refetch();
    summaryQuery.refetch();
    svcQuery.refetch();
    resourceQuery.refetch();
  };

  const yoyPriorTotal = showYtd ? compareTotal : null;
  const yoyPct = showYtd && compareTotal > 0
    ? ((total - compareTotal) / compareTotal) * 100
    : null;
  const yoyYear = showYtd ? new Date().getFullYear() - 1 : null;

  const scrollToBreakdown = () => {
    breakdownRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  if (!subscription) {
    return (
      <section className="cost-explorer-v2" aria-label="Cost explorer">
        <SubscriptionRequired message="Select a subscription to view cost data." />
      </section>
    );
  }

  if (isError && !summary && !costQuery.data) {
    return (
      <section className="cost-explorer-v2" aria-label="Cost explorer">
        <QueryErrorState
          error={costQuery.error || summaryQuery.error}
          onRetry={handleRetry}
          title="Could not load cost data"
        />
      </section>
    );
  }

  return (
    <section
      className="cost-explorer-v2"
      aria-label="Cost explorer"
      style={{ '--ce-currency': `"${currency}"` }}
    >
      <CostExplorerPageHead
        periodLabel={periodTitle}
        costSyncAt={costSyncAt}
        onExport={handleExport}
        exportLoading={exporting}
        adminActions={isAdmin ? (
          <AdminOnly>
            <FetchCostsButton onClick={sync} loading={syncing} />
          </AdminOnly>
        ) : null}
      />

      {isError && (summary || costQuery.data) && (
        <div className="panel" role="alert" style={{ marginBottom: 16 }}>
          <QueryErrorState
            error={costQuery.error || summaryQuery.error}
            onRetry={handleRetry}
            title="Some cost data could not be refreshed"
          />
        </div>
      )}

      <CostExplorerTimeFilter
        timeframe={timeframe}
        onTimeframeChange={setTimeframe}
        granularity={granularity}
        onGranularityChange={setGranularity}
        customFrom={customFrom}
        customTo={customTo}
        onCustomFromChange={setCustomFrom}
        onCustomToChange={setCustomTo}
        rangeLabel={rangeLabelText}
      />

      {syncRequired && !isLoading && !hasData && (
        <div className="ce-sync-banner" role="status">
          {isAdmin
            ? <>No synced cost data yet. Use <strong>Fetch costs</strong> to sync from Azure Cost Management.</>
            : 'No synced cost data yet. Ask an administrator to sync costs from Azure.'}
        </div>
      )}

      <CostExplorerHeroGrid
        currency={currency}
        spendLabel={periodTitle}
        total={total}
        periodDelta={periodDelta}
        compareTotal={compareTotal}
        comparePeriodLabel={comparePeriodLabel}
        projectedMonthEnd={projected}
        avgDaily={avgDaily}
        daysElapsed={daysElapsed}
        cumulativeTotal={total}
        rangeLabel={rangeLabelText}
        dailyPoints={dailyPoints}
        compareDailyPoints={compareDailyPoints}
        loading={isLoading}
        showYoy={showYtd && yoyPct != null}
        yoyPct={yoyPct}
        yoyPriorTotal={yoyPriorTotal}
        yoyYear={yoyYear}
        isPartialPeriod={isPartialPeriod}
      />

      <CostExplorerBudgetStrip
        budgets={budgetsQuery.data}
        currency={currency}
        currentSpend={total}
        projectedMonthEnd={projected}
        daysRemaining={daysRemaining}
        avgDaily={avgDaily}
      />

      <CostExplorerCommandBar
        search={search}
        onSearchChange={setSearch}
        serviceFilter={serviceFilter}
        onServiceFilterChange={setServiceFilter}
        services={services}
        resourceGroupFilter={rgFilter}
        onResourceGroupFilterChange={setRgFilter}
        resourceGroups={resourceGroups}
        tagFilter={tagFilter}
        onTagFilterChange={setTagFilter}
        tags={[]}
        chipFilter={chipFilter}
        onChipFilterChange={setChipFilter}
      />

      <CostExplorerTrendPanel
        dailyChart={dailyChart}
        cumulativeChart={cumulativeChart}
        compareDailyChart={compareDailyPoints}
        forecastPoints={forecastPoints}
        currency={currency}
        rangeLabel={rangeLabelText}
        avgDaily={avgDaily}
        comparePeriodLabel={comparePeriodLabel}
        loading={costQuery.isLoading}
        isMtd={isMtd}
      />

      <CostExplorerComparisonGrid
        dailyChart={dailyPoints}
        compareDailyChart={compareDailyPoints}
        momBars={momBars}
        comparisonServices={comparisonQuery.data?.services}
        ytdStacks={ytdStacks}
        currency={currency}
        comparePeriodLabel={comparePeriodLabel}
        showYtd={showYtd}
        loading={comparisonQuery.isLoading || monthlyQuery.isLoading}
      />

      <div className="ce-split-row" ref={breakdownRef}>
        <CostExplorerBreakdown
          serviceRows={serviceChart.map((r, i) => ({
            key: r.name,
            name: r.name,
            cost: r.cost,
            widthPct: serviceChart[0]?.cost ? Math.round((r.cost / serviceChart[0].cost) * 100) : 0,
            color: ['#60a5fa', '#f87171', '#fbbf24', '#a78bfa', '#34d399', '#94a3b8'][i % 6],
          }))}
          rgRows={rgRows}
          regionRows={regionRows}
          tagRows={[]}
          total={total}
          currency={currency}
        />
        <CostExplorerAllocation
          total={total}
          amortizedTotal={summary?.amortized_total ?? null}
          currency={currency}
          serviceRows={serviceChart.map((r, i) => ({
            key: r.name,
            name: r.name,
            cost: r.cost,
            color: ['#60a5fa', '#f87171', '#a78bfa', '#34d399', '#94a3b8'][i % 5],
          }))}
        />
      </div>

      <div className="ce-layout">
        <CostExplorerTopSpend
          rows={filteredSpendRows}
          currency={currency}
          subscription={subscription}
          costLabel={isMtd ? 'MTD cost' : 'Period cost'}
          sparkTitle={isMtd ? 'Daily cost (MTD)' : 'Daily cost trend'}
          anomalyResourceIds={anomalyResourceIds}
          loading={resourceQuery.isLoading}
        />
        <CostExplorerAnomalies
          dailyAnomalies={dailyAnomalyQuery.data}
          serviceAnomalies={serviceAnomalyQuery.data}
          velocity={velocity}
          currency={currency}
          loading={dailyAnomalyQuery.isLoading || serviceAnomalyQuery.isLoading}
          onViewBreakdown={scrollToBreakdown}
        />
      </div>
    </section>
  );
}
