import React from 'react';
import { formatCurrency } from '../utils/format';
import { resourceCostTrend, resourceBilledMtd, resourceRetailMonthly, resourceRetailCurrency } from '../utils/costCurrency';
import TrendBadge from './visual/TrendBadge';
import { CostDailyTrendChart } from './cost/CostTrendChart';
import { DrawerSectionSkeleton } from './DrawerBodySkeleton';
import useDrawerResourceCostTrend from '../hooks/useDrawerResourceCostTrend';

const RETAIL_TOOLTIP = 'Catalog pricing from Azure Retail Prices — estimated monthly, not your invoice.';

export default function ResourceDrawerCostSection({
  resource,
  resourceId,
  subscriptionId,
  currency = 'CAD',
  totalCost = 0,
  analysisData = null,
}) {
  const billedMtd = resourceBilledMtd(resource) || totalCost;
  const retailMonthly = resourceRetailMonthly(resource);
  const retailCurrency = resourceRetailCurrency(resource, currency);
  const costTrend = resourceCostTrend(resource);
  const trends = analysisData?.trends;

  const {
    chartData,
    hasChart,
    isLoading,
    isSyncing,
    syncError,
  } = useDrawerResourceCostTrend({
    subscriptionId,
    resourceId,
    enabled: Boolean(subscriptionId && resourceId),
  });

  return (
    <div className="drawer-cost">
      <section className="insight-drawer__property-group drawer-cost__summary-section">
        <h4 className="insight-drawer__property-group-title">Period spend</h4>
        <div className="drawer-cost__summary">
          <div className="drawer-cost__summary-grid">
            <div className="drawer-cost__summary-item">
              <span className="drawer-cost__summary-label">Billed MTD</span>
              <div className="drawer-cost__summary-main">
                <strong className="drawer-cost__summary-value" title="Month to date (billed)">
                  {billedMtd > 0 ? formatCurrency(billedMtd, { currency }) : '—'}
                </strong>
                {billedMtd > 0 && (
                  <TrendBadge deltaAmount={costTrend} currency={currency} invert />
                )}
              </div>
            </div>
            <div className="drawer-cost__summary-item">
              <span className="drawer-cost__summary-label" title={RETAIL_TOOLTIP}>Retail estimate</span>
              <strong className="drawer-cost__summary-value drawer-cost__summary-value--retail">
                {retailMonthly > 0
                  ? `${formatCurrency(retailMonthly, { currency: retailCurrency })}/mo`
                  : '—'}
              </strong>
            </div>
          </div>
          {trends?.cost_vs_prev_month_pct != null && (
            <p className="drawer-cost__summary-note">
              {trends.cost_trajectory === 'increasing' ? 'Up' : trends.cost_trajectory === 'decreasing' ? 'Down' : 'Change'}
              {' '}
              {Math.abs(trends.cost_vs_prev_month_pct)}% vs prior billed month
            </p>
          )}
        </div>
      </section>

      <section className="insight-drawer__property-group drawer-cost__trend-section">
        <h4 className="insight-drawer__property-group-title">Spend trend</h4>
        <div className="drawer-cost__trend">
          {isLoading && <DrawerSectionSkeleton rows={3} />}
          {!isLoading && isSyncing && (
            <p className="insight-drawer__empty insight-drawer__empty--compact" role="status" aria-live="polite">
              Syncing spend history…
            </p>
          )}
          {!isLoading && !isSyncing && hasChart && (
            <CostDailyTrendChart
              data={chartData}
              currency={currency}
              fieldLabel="Spend"
              variant="line"
            />
          )}
          {!isLoading && !isSyncing && syncError && (
            <p className="insight-drawer__empty insight-drawer__empty--compact insight-drawer__empty--error" role="alert">
              {syncError}
            </p>
          )}
          {!isLoading && !isSyncing && !syncError && !hasChart && (
            <p className="insight-drawer__empty insight-drawer__empty--compact">
              No spend recorded for this resource in the last 28 days.
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
