import React, { useContext, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { TrendingUp } from 'lucide-react';
import { increaseColorClass } from '../utils/visualPolish';
import { AppCtx } from '../App';
import { useAuth } from '../context/AuthContext';
import { fetchCosts, fetchCostByService, fetchCostSummary, fetchCostChanges, fetchResourceTypes } from '../api/azure';
import PageHeader from '../components/PageHeader';
import FilterBar from '../components/FilterBar';
import ResourceTypeFilter from '../components/ResourceTypeFilter';
import CostExplorerHero from '../components/cost/CostExplorerHero';
import { CostDailyTrendChart, CostServiceBarChart } from '../components/cost/CostTrendChart';
import useCostSync from '../hooks/useCostSync';
import { PAGE_ICONS } from '../config/assetIcons';
import { formatCurrency, formatDateRange, formatIsoDate } from '../utils/format';
import { billingAmount, azureFieldLabel, DISPLAY_CURRENCY } from '../utils/costCurrency';
import { textIncludes } from '../utils/filterUtils';
import { SubscriptionRequired, QueryErrorState } from '../components/QueryStates';
import {
  COST_TIMEFRAME_OPTIONS,
  costTimeframeLabel,
  buildCostQueryParams,
  defaultCompareTimeframe,
  previousCustomRange,
} from '../config/costTimeframes';
import { normalizeResourceTypeSelection, withResourceTypes } from '../utils/resourceTypeFilter';

function ChartLoading({ message = 'Loading…' }) {
  return (
    <div className="cost-explorer-chart-loading" role="status" aria-live="polite">
      <div className="spin" />
      <p>{message}</p>
    </div>
  );
}

const TIMEFRAME_OPTIONS = COST_TIMEFRAME_OPTIONS;
const VALID_TIMEFRAMES = new Set(COST_TIMEFRAME_OPTIONS.map((opt) => opt.value));

const PERIOD_PRESETS = [
  { key: '7d', label: '7d', value: 'Last7Days' },
  { key: '30d', label: '30d', value: 'Last30Days' },
  { key: 'MTD', label: 'MTD', value: 'MonthToDate' },
  { key: '90d', label: '90d', value: 'Last3Months' },
  { key: 'YTD', label: 'YTD', value: 'ThisYear' },
];

const SERVICE_BAR_COLORS = ['#0284c7', '#0ea5e9', '#38bdf8', '#0369a1', '#7dd3fc', '#6366f1', '#8b5cf6', '#94a3b8'];

function parseCostRows(resp) {
  if (!resp) return [];
  const props = resp.properties || resp;
  const cols = (props.columns || []).map((c) => c.name);
  const rows = props.rows || [];
  return rows.map((r) => {
    const obj = {};
    cols.forEach((c, i) => { obj[c] = r[i]; });
    return obj;
  });
}

function CostPanel({ title, subtitle, children, empty, emptyAction }) {
  return (
    <article className="portal-panel card cost-explorer-panel">
      <header className="portal-panel__head">
        <div>
          <h3 className="portal-panel__title">{title}</h3>
          {subtitle && <p className="portal-panel__desc">{subtitle}</p>}
        </div>
      </header>
      {empty ? (
        <div className="portal-panel__empty">
          <p>{empty}</p>
          {emptyAction}
        </div>
      ) : children}
    </article>
  );
}

export default function CostExplorer() {
  const { subscription, billingCurrency, subscriptionOptions } = useContext(AppCtx);
  const { isAdmin } = useAuth();
  const [searchParams] = useSearchParams();
  const urlTimeframe = searchParams.get('timeframe');
  const [timeframe, setTimeframe] = useState(() => (
    urlTimeframe && VALID_TIMEFRAMES.has(urlTimeframe) ? urlTimeframe : 'MonthToDate'
  ));
  const [customFrom, setCustomFrom] = useState('');
  const [customTo, setCustomTo] = useState('');
  const [serviceSearch, setServiceSearch] = useState('');
  const [compareEnabled, setCompareEnabled] = useState(false);
  const [compareTimeframe, setCompareTimeframe] = useState('TheLastMonth');
  const [compareCustomFrom, setCompareCustomFrom] = useState('');
  const [compareCustomTo, setCompareCustomTo] = useState('');
  const [selectedResourceTypes, setSelectedResourceTypes] = useState([]);

  const { data: typeCatalog } = useQuery({
    queryKey: ['resource-types-catalog'],
    queryFn: fetchResourceTypes,
    staleTime: 24 * 60 * 60_000,
  });

  const effectiveResourceTypes = useMemo(
    () => normalizeResourceTypeSelection(selectedResourceTypes, typeCatalog),
    [selectedResourceTypes, typeCatalog],
  );

  useEffect(() => {
    setCompareTimeframe(defaultCompareTimeframe(timeframe));
    if (timeframe === 'Custom' && customFrom && customTo) {
      const prev = previousCustomRange(customFrom, customTo);
      if (prev) {
        setCompareCustomFrom(prev.from_date);
        setCompareCustomTo(prev.to_date);
      }
    } else if (timeframe === 'Last7Days') {
      const today = new Date();
      const end = new Date(today);
      end.setDate(end.getDate() - 7);
      const start = new Date(end);
      start.setDate(start.getDate() - 6);
      const fmt = (d) => d.toISOString().slice(0, 10);
      setCompareCustomFrom(fmt(start));
      setCompareCustomTo(fmt(end));
    }
  }, [timeframe, customFrom, customTo]);

  const rangeParams = useMemo(
    () => withResourceTypes(
      buildCostQueryParams({
        subscription_id: subscription,
        timeframe,
        from_date: timeframe === 'Custom' ? customFrom : undefined,
        to_date: timeframe === 'Custom' ? customTo : undefined,
      }),
      effectiveResourceTypes,
      typeCatalog,
    ),
    [subscription, timeframe, customFrom, customTo, effectiveResourceTypes, typeCatalog],
  );

  const rangeReady = timeframe !== 'Custom' || (customFrom && customTo);
  const compareUsesCustom = compareTimeframe === 'Custom' || timeframe === 'Last7Days';
  const compareReady = !compareEnabled || (
    compareUsesCustom ? (compareCustomFrom && compareCustomTo) : true
  );

  const compareParams = useMemo(() => {
    if (!compareEnabled) return null;
    const base = compareUsesCustom
      ? buildCostQueryParams({
        subscription_id: subscription,
        timeframe: 'Custom',
        from_date: compareCustomFrom,
        to_date: compareCustomTo,
      })
      : buildCostQueryParams({
        subscription_id: subscription,
        timeframe: compareTimeframe,
      });
    return withResourceTypes(base, effectiveResourceTypes, typeCatalog);
  }, [
    compareEnabled,
    compareUsesCustom,
    subscription,
    compareTimeframe,
    compareCustomFrom,
    compareCustomTo,
    effectiveResourceTypes,
    typeCatalog,
  ]);

  const subLabel = subscriptionOptions.find((s) => s.subscriptionId === subscription)?.displayName;

  const { sync, syncing, lastChanges } = useCostSync({
    subscription,
    invalidateKeys: [
      ['costs', subscription],
      ['cost-summary', subscription],
      ['cost-by-svc', subscription],
      ['cost-changes', subscription],
      ['dashboard-overview', subscription],
      ['resources-from-cost', subscription],
      ['resource-counts', subscription],
    ],
  });

  const {
    data: costData,
    isLoading: loadCost,
    isError: costError,
    error: costErr,
    refetch: refetchCost,
  } = useQuery({
    queryKey: ['costs', subscription, timeframe, customFrom, customTo, effectiveResourceTypes],
    queryFn: () => fetchCosts({ ...rangeParams, granularity: 'Daily' }),
    enabled: !!subscription && rangeReady,
    staleTime: 5 * 60_000,
  });

  const { data: compareCostData, isLoading: loadCompareCost } = useQuery({
    queryKey: ['costs-compare', subscription, compareParams],
    queryFn: () => fetchCosts({ ...compareParams, granularity: 'Daily' }),
    enabled: !!subscription && compareEnabled && compareReady && !!compareParams,
    staleTime: 5 * 60_000,
  });

  const { data: compareSummary } = useQuery({
    queryKey: ['cost-summary-compare', subscription, compareParams],
    queryFn: () => fetchCostSummary(compareParams),
    enabled: !!subscription && compareEnabled && compareReady && !!compareParams,
    staleTime: 5 * 60_000,
  });

  const {
    data: summary,
    isLoading: loadSummary,
    isError: summaryError,
    error: summaryErr,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: ['cost-summary', subscription, timeframe, customFrom, customTo, effectiveResourceTypes],
    queryFn: () => fetchCostSummary(rangeParams),
    enabled: !!subscription && rangeReady,
    staleTime: 5 * 60_000,
  });

  const { data: svcData, isLoading: loadSvc } = useQuery({
    queryKey: ['cost-by-svc', subscription, timeframe, customFrom, customTo, effectiveResourceTypes],
    queryFn: () => fetchCostByService(rangeParams),
    enabled: !!subscription && rangeReady,
    staleTime: 5 * 60_000,
  });

  const { data: costChanges } = useQuery({
    queryKey: ['cost-changes', subscription, timeframe],
    queryFn: () => fetchCostChanges({ subscription_id: subscription }),
    enabled: !!subscription,
    staleTime: 5 * 60_000,
  });

  const changes = lastChanges || costChanges;
  const increases = (changes?.services || []).filter((s) => (s.delta_billing || 0) > 0);
  const syncRequired = costData?.sync_required || summary?.sync_required || svcData?.sync_required;
  const isLoading = loadCost || loadSummary;
  const isError = costError || summaryError;

  const mtdStart = summary?.period_start || summary?.mtd_start || changes?.mtd_start;
  const mtdEnd = summary?.period_end || summary?.mtd_end || changes?.mtd_end;
  const mtdPeriodLabel = mtdStart && mtdEnd ? formatDateRange(mtdStart, mtdEnd) : null;

  const dailyRows = parseCostRows(costData?.data);
  const compareDailyRows = parseCostRows(compareCostData?.data);
  const svcRows = parseCostRows(svcData);

  const currency = billingCurrency || DISPLAY_CURRENCY;
  const fieldLabel = azureFieldLabel(currency);

  const dailyChart = useMemo(() => {
    const current = dailyRows
      .filter((r) => r.UsageDate || r.BillingPeriodStartDate)
      .map((r) => ({
        date: String(r.UsageDate || r.BillingPeriodStartDate || '').slice(0, 10),
        dateLabel: formatIsoDate(String(r.UsageDate || r.BillingPeriodStartDate || '').slice(0, 10)),
        cost: billingAmount(r),
      }))
      .filter((r) => {
        if (!mtdStart || !mtdEnd) return true;
        return r.date >= mtdStart && r.date <= mtdEnd;
      })
      .sort((a, b) => a.date.localeCompare(b.date));

    if (!compareEnabled || !compareDailyRows.length) return current;

    const compare = compareDailyRows
      .map((r) => ({
        date: String(r.UsageDate || r.BillingPeriodStartDate || '').slice(0, 10),
        cost: billingAmount(r),
      }))
      .sort((a, b) => a.date.localeCompare(b.date));

    return current.map((row, index) => {
      const cmp = compare[index];
      return {
        ...row,
        compareCost: cmp?.cost ?? null,
        compareDateLabel: cmp ? formatIsoDate(cmp.date) : null,
      };
    });
  }, [dailyRows, compareDailyRows, compareEnabled, mtdStart, mtdEnd]);

  const svcChart = useMemo(
    () => svcRows
      .map((r) => ({
        name: r.ServiceName || 'Unassigned',
        cost: billingAmount(r),
      }))
      .sort((a, b) => b.cost - a.cost),
    [svcRows],
  );

  const topServicesChart = useMemo(() => svcChart.slice(0, 8), [svcChart]);

  const filteredSvcChart = useMemo(() => {
    if (!serviceSearch) return svcChart;
    return svcChart.filter((row) => textIncludes(row.name, serviceSearch));
  }, [svcChart, serviceSearch]);

  const hasServiceFilter = !!serviceSearch;

  const total = useMemo(
    () => summary?.pretax_total ?? dailyChart.reduce((s, r) => s + r.cost, 0),
    [summary, dailyChart],
  );

  const compareTotal = compareSummary?.pretax_total ?? null;
  const periodDelta = compareEnabled && compareTotal != null ? total - compareTotal : null;
  const periodDeltaPct = compareEnabled && compareTotal > 0
    ? ((total - compareTotal) / compareTotal) * 100
    : null;
  const comparePeriodLabel = compareUsesCustom
    ? (compareCustomFrom && compareCustomTo ? formatDateRange(compareCustomFrom, compareCustomTo) : null)
    : costTimeframeLabel(compareTimeframe);

  const daysElapsed = useMemo(() => {
    if (!mtdStart || !mtdEnd) return new Date().getDate();
    const start = new Date(`${mtdStart}T00:00:00`);
    const end = new Date(`${mtdEnd}T00:00:00`);
    return Math.max(1, Math.round((end - start) / 86400000) + 1);
  }, [mtdStart, mtdEnd]);

  const projectedMonthEnd = timeframe === 'MonthToDate' || timeframe === 'BillingMonthToDate'
    ? (total / daysElapsed) * 30
    : null;

  const handleRetry = () => {
    refetchCost();
    refetchSummary();
  };

  const timeframeSelect = (
    <div className="cost-explorer-timeframe-group">
      <div className="period-btn-group" role="group" aria-label="Time period">
        {PERIOD_PRESETS.map((preset) => (
          <button
            key={preset.key}
            type="button"
            className={`period-btn${timeframe === preset.value ? ' active' : ''}`}
            onClick={() => setTimeframe(preset.value)}
          >
            {preset.label}
          </button>
        ))}
      </div>
      <select
        value={timeframe}
        onChange={(e) => setTimeframe(e.target.value)}
        aria-label="More timeframes"
        className="cost-explorer-timeframe cost-explorer-timeframe--more"
      >
        {TIMEFRAME_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
      {timeframe === 'Custom' && (
        <div className="cost-explorer-custom-range">
          <input
            type="date"
            value={customFrom}
            onChange={(e) => setCustomFrom(e.target.value)}
            aria-label="Start date"
          />
          <span aria-hidden>–</span>
          <input
            type="date"
            value={customTo}
            onChange={(e) => setCustomTo(e.target.value)}
            aria-label="End date"
          />
        </div>
      )}
      <label className="cost-explorer-compare-toggle">
        <input
          type="checkbox"
          checked={compareEnabled}
          onChange={(e) => setCompareEnabled(e.target.checked)}
        />
        Compare period
      </label>
      {compareEnabled && !compareUsesCustom && (
        <select
          value={compareTimeframe}
          onChange={(e) => setCompareTimeframe(e.target.value)}
          aria-label="Comparison period"
          className="cost-explorer-timeframe cost-explorer-timeframe--compare"
        >
          {TIMEFRAME_OPTIONS.filter((opt) => opt.value !== 'Custom').map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      )}
      {compareEnabled && compareUsesCustom && (
        <div className="cost-explorer-custom-range">
          <input
            type="date"
            value={compareCustomFrom}
            onChange={(e) => setCompareCustomFrom(e.target.value)}
            aria-label="Compare start date"
          />
          <span aria-hidden>–</span>
          <input
            type="date"
            value={compareCustomTo}
            onChange={(e) => setCompareCustomTo(e.target.value)}
            aria-label="Compare end date"
          />
        </div>
      )}
    </div>
  );

  return (
    <div className="page-shell cost-explorer-page">
      <PageHeader
        title="Cost explorer"
        iconKey={PAGE_ICONS.costs}
      >
        {subscription && timeframeSelect}
      </PageHeader>

      {!subscription && (
        <SubscriptionRequired message="Select a subscription to view cost data." />
      )}

      {subscription && isError && (
        <QueryErrorState
          error={costErr || summaryErr}
          onRetry={handleRetry}
          title="Could not load cost data"
        />
      )}

      {subscription && !isError && (
        <div className="cost-explorer-layout">
          {syncRequired && !isLoading && (
            <div className="cost-explorer-banner card" role="status">
              {isAdmin
                ? <>No synced cost data yet. Use <strong>Fetch costs</strong> in the hero to sync from Azure Cost Management.</>
                : 'No synced cost data yet. Ask an administrator to sync costs from Azure.'}
            </div>
          )}

          <div className="cost-explorer-layout__filters">
            <ResourceTypeFilter
              selected={selectedResourceTypes}
              onChange={setSelectedResourceTypes}
            />
          </div>

          <CostExplorerHero
            subscriptionLabel={subLabel}
            currency={currency}
            timeframe={timeframe}
            mtdStart={mtdStart}
            mtdEnd={mtdEnd}
            total={total}
            topService={svcChart[0]}
            serviceCount={svcChart.length}
            mtdPeriodLabel={mtdPeriodLabel}
            lastSyncedAt={summary?.synced_at}
            isLoading={isLoading}
            onSync={sync}
            syncing={syncing}
            canSync={isAdmin}
            compareTotal={compareEnabled ? compareTotal : null}
            comparePeriodLabel={compareEnabled ? comparePeriodLabel : null}
            periodDelta={periodDelta}
            periodDeltaPct={periodDeltaPct}
            projectedMonthEnd={projectedMonthEnd}
          />

          <section className="dashboard-section">
            <h3 className="dashboard-section__title dashboard-section__title--bar">Spend trends</h3>
            <div className="dashboard-row dashboard-row--primary">
              <CostPanel
                title={`Daily cost (${currency})`}
                subtitle={compareEnabled
                  ? `${costTimeframeLabel(timeframe)} vs ${comparePeriodLabel || 'previous period'}`
                  : costTimeframeLabel(timeframe)}
                empty={!loadCost && dailyChart.length === 0 ? 'No daily cost data available.' : null}
              >
                <CostDailyTrendChart
                  data={dailyChart}
                  currency={currency}
                  fieldLabel={fieldLabel}
                  compareLabel={comparePeriodLabel}
                  loading={loadCost || (compareEnabled && loadCompareCost)}
                />
              </CostPanel>

              <CostPanel
                title={`Top services (${currency})`}
                subtitle="Highest spend in period"
                empty={!loadSvc && topServicesChart.length === 0 ? 'No service data.' : null}
              >
                <CostServiceBarChart
                  data={topServicesChart}
                  currency={currency}
                  fieldLabel={fieldLabel}
                  loading={loadSvc}
                  colors={SERVICE_BAR_COLORS}
                />
              </CostPanel>
            </div>
          </section>

          {changes?.has_previous && increases.length > 0 && (
            <section className="dashboard-section">
              <h3 className="dashboard-section__title dashboard-section__title--bar">Cost changes</h3>
              <article className="card cost-explorer-increases">
                <header className="cost-explorer-increases__head">
                  <TrendingUp size={18} aria-hidden />
                  <div>
                    <h3 className="portal-panel__title">Increased since last fetch</h3>
                    <p className="portal-panel__desc">
                      {mtdPeriodLabel ? `MTD ${mtdPeriodLabel}` : 'Month to date'}
                      {changes.previous_synced_at
                        ? ` · compared to ${formatIsoDate(changes.previous_synced_at.slice(0, 10))}`
                        : ''}
                    </p>
                  </div>
                </header>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Service</th>
                        <th>Previous MTD</th>
                        <th>Current MTD</th>
                        <th>Increase</th>
                      </tr>
                    </thead>
                    <tbody>
                      {increases.slice(0, 10).map((row) => {
                        const pct = row.previous_billing > 0
                          ? ((row.delta_billing / row.previous_billing) * 100)
                          : 0;
                        return (
                        <tr key={row.service_name}>
                          <td className="cost-explorer-table__name">{row.service_name}</td>
                          <td>{formatCurrency(row.previous_billing, { currency })}</td>
                          <td>{formatCurrency(row.current_billing, { currency })}</td>
                          <td className="cost-change-cell">
                            <span className={`cost-change-cell__amount ${increaseColorClass(pct)}`}>
                              +{formatCurrency(row.delta_billing, { currency })}
                            </span>
                            <span className="cost-change-cell__pct">↑ {pct.toFixed(1)}%</span>
                          </td>
                        </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </article>
            </section>
          )}

          <section className="dashboard-section">
            <h3 className="dashboard-section__title dashboard-section__title--bar">All services</h3>
            <CostPanel
              title={`Cost by service (${currency})`}
              subtitle={`${filteredSvcChart.length} of ${svcChart.length} services`}
              empty={svcChart.length === 0 ? 'No service data.' : null}
            >
              {svcChart.length > 0 && (
                <>
                  <FilterBar
                    search={{
                      value: serviceSearch,
                      onChange: setServiceSearch,
                      placeholder: 'Filter services…',
                    }}
                    onClear={hasServiceFilter ? () => setServiceSearch('') : undefined}
                    resultCount={{
                      shown: filteredSvcChart.length,
                      total: svcChart.length,
                      label: 'services',
                    }}
                    className="filter-bar--compact"
                  />
                  <div className="table-wrap cost-explorer-table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Service</th>
                          <th>{fieldLabel}</th>
                          <th>Share</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filteredSvcChart.map((row) => {
                          const share = total > 0 ? (row.cost / total) * 100 : 0;
                          return (
                            <tr key={row.name}>
                              <td className="cost-explorer-table__name">{row.name}</td>
                              <td>{formatCurrency(row.cost, { currency })}</td>
                              <td>
                                <div className="cost-explorer-share">
                                  <div className="cost-explorer-share__bar-wrap">
                                    <div
                                      className="cost-explorer-share__bar"
                                      style={{ width: `${Math.min(100, share)}%` }}
                                    />
                                  </div>
                                  <span className="cost-explorer-share__pct">
                                    {share >= 0.1 ? `${share.toFixed(1)}%` : '<0.1%'}
                                  </span>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </CostPanel>
          </section>
        </div>
      )}
    </div>
  );
}
