import React from 'react';
import { Link } from 'react-router-dom';
import { toDisplayText } from '../../utils/formatDisplay';
import { formatCurrency, formatDateRange } from '../../utils/format';
import AdminOnly from '../AdminOnly';
import TrendBadge from '../visual/TrendBadge';

function HeroMetric({
  label,
  value,
  sub,
  tone = 'default',
  href,
  trendPct,
  trendAmount,
  currency,
}) {
  const content = (
    <div className={`dashboard-hero__metric dashboard-hero__metric--${tone}`}>
      <div className="dashboard-hero__metric-top">
        <span className="dashboard-hero__metric-value trend-indicator">{value}</span>
        {trendAmount != null && Number(trendAmount) !== 0 && (
          <TrendBadge deltaAmount={trendAmount} currency={currency} invert />
        )}
        {trendAmount == null && trendPct != null && <TrendBadge deltaPct={trendPct} invert />}
      </div>
      <span className="dashboard-hero__metric-label">{label}</span>
      {sub && <span className="dashboard-hero__metric-sub">{sub}</span>}
    </div>
  );
  if (href) {
    return (
      <Link to={href} className="dashboard-hero__metric-link">
        {content}
      </Link>
    );
  }
  return content;
}

function HeroSkeleton() {
  return (
    <section className="dashboard-hero dashboard-hero--loading" aria-busy="true">
      <div className="dashboard-hero__glow" aria-hidden />
      <div className="dashboard-hero__content">
        <div className="dashboard-hero__main">
          <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--sm" />
          <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--lg" />
          <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--md" />
        </div>
        <div className="dashboard-hero__metrics dashboard-hero__metrics--secondary dashboard-hero__metrics--grouped">
          <div className="dashboard-hero__metric-group dashboard-hero__metric-group--cost">
            {[1, 2].map((i) => (
              <div key={i} className="dashboard-kpi-skeleton dashboard-kpi-skeleton--metric" />
            ))}
          </div>
          <div className="dashboard-hero__metric-group dashboard-hero__metric-group--resources">
            {[1, 2, 3].map((i) => (
              <div key={i} className="dashboard-kpi-skeleton dashboard-kpi-skeleton--metric" />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

export default function DashboardHero({
  subscriptionLabel,
  portal,
  costSummary,
  ytdSummary,
  optimizationSummary,
  budgets,
  currency,
  isLoading,
  resourceTypeFilterActive = false,
  costPeriodLabel,
  costPeriod = 'MonthToDate',
}) {
  if (isLoading && !portal) {
    return <HeroSkeleton />;
  }

  if (!portal) {
    return null;
  }

  const billingCurrency = currency || costSummary?.billing_currency || 'CAD';
  const mtdAmount = costSummary?.pretax_total ?? costSummary?.cost_usd_total ?? 0;
  const ytdAmount = ytdSummary?.pretax_total ?? ytdSummary?.cost_usd_total ?? 0;
  const ytdPeriodStart = ytdSummary?.period_start;
  const ytdPeriodEnd = ytdSummary?.period_end;
  const ytdPeriodLabel = ytdPeriodStart && ytdPeriodEnd
    ? formatDateRange(ytdPeriodStart, ytdPeriodEnd)
    : null;
  const openFindings = optimizationSummary?.open_findings ?? 0;
  const estSavings = optimizationSummary?.total_estimated_savings_usd ?? 0;
  const periodStart = costSummary?.period_start || costSummary?.mtd_start;
  const periodEnd = costSummary?.period_end || costSummary?.mtd_end;
  const mtdDateRangeLabel = periodStart && periodEnd
    ? formatDateRange(periodStart, periodEnd)
    : null;

  const kpisById = Object.fromEntries((portal.kpis || []).map((k) => [k.id, k]));
  const totalResources = kpisById.total_resources?.value ?? 0;
  const weeklyCost = kpisById.weekly_cost?.value ?? 0;
  const projectedMonthly = kpisById.monthly_trend?.value ?? 0;
  const mtdDelta = portal.hero_deltas?.mtd_delta_usd ?? kpisById.monthly_trend?.mtd_delta_usd;

  const primaryBudget = (budgets || []).find((b) => b.amount > 0);
  const budgetRemaining = primaryBudget
    ? Math.max(0, primaryBudget.amount - (primaryBudget.currentSpend ?? mtdAmount))
    : null;

  const heroActions = portal.hero_actions || [
    { id: 'actions', label: 'View actions', href: '/optimization-hub?tab=actions' },
    { id: 'costs', label: 'Cost explorer', href: '/costs' },
    { id: 'sync_center', label: 'Sync center', href: '/admin/optimization', admin_only: true },
  ];

  const periodLabel = resourceTypeFilterActive
    ? `Subscription spend — filtered (${billingCurrency})`
    : (costPeriodLabel
      ? `Subscription spend · ${costPeriodLabel} (${billingCurrency})`
      : `Subscription spend (${billingCurrency})`);
  const ytdLabel = resourceTypeFilterActive
    ? `Subscription YTD — filtered (${billingCurrency})`
    : `Subscription YTD (${billingCurrency})`;

  return (
    <section className="dashboard-hero">
      <div className="dashboard-hero__glow" aria-hidden />
      <div className="dashboard-hero__content">
        <div className="dashboard-hero__main">
          <p className="dashboard-hero__eyebrow">
            Subscription overview
            {costPeriodLabel ? ` · ${costPeriodLabel}` : ''}
          </p>
          <h2 className="dashboard-hero__title">
            {subscriptionLabel ? toDisplayText(subscriptionLabel) : 'Dashboard'}
          </h2>
          <div className="dashboard-hero__spend-row">
            <div className="dashboard-hero__primary-metric">
              <HeroMetric
                label={periodLabel}
                value={formatCurrency(mtdAmount, { currency: billingCurrency, decimals: 0 })}
                sub={mtdDateRangeLabel
                  ? `${mtdDateRangeLabel}${resourceTypeFilterActive ? ' · selected types only' : ''}`
                  : (resourceTypeFilterActive ? 'Selected types only' : 'This billing period')}
                tone="default"
                href={`/costs?timeframe=${encodeURIComponent(costPeriod)}`}
                trendAmount={mtdDelta}
                currency={billingCurrency}
              />
            </div>
            <div className="dashboard-hero__primary-metric dashboard-hero__primary-metric--ytd">
              <HeroMetric
                label={ytdLabel}
                value={formatCurrency(ytdAmount, { currency: billingCurrency, decimals: 0 })}
                sub={ytdPeriodLabel
                  ? `${ytdPeriodLabel}${resourceTypeFilterActive ? ' · selected types only' : ''}`
                  : (resourceTypeFilterActive ? 'Selected types only' : 'Year to date')}
                tone="default"
                href="/costs?timeframe=ThisYear"
              />
            </div>
          </div>
          <div className="dashboard-hero__actions">
            {heroActions.map((action) => {
              const btn = (
                <Link key={action.id} to={action.href} className="btn btn-ghost btn-sm">
                  {action.label}
                </Link>
              );
              if (action.admin_only) {
                return <AdminOnly key={action.id}>{btn}</AdminOnly>;
              }
              return btn;
            })}
          </div>
        </div>
        <div
          className="dashboard-hero__metrics dashboard-hero__metrics--secondary dashboard-hero__metrics--grouped"
          aria-label="Subscription metrics"
        >
          <div
            className="dashboard-hero__metric-group dashboard-hero__metric-group--cost"
            role="group"
            aria-label="Cost"
          >
            <HeroMetric
              label={`Weekly cost (${billingCurrency})`}
              value={formatCurrency(weeklyCost, { currency: billingCurrency, decimals: 0 })}
              tone="default"
              href="/costs"
              trendAmount={kpisById.weekly_cost?.delta_usd}
              currency={billingCurrency}
            />
            <HeroMetric
              label={`Forecast month (${billingCurrency})`}
              value={formatCurrency(projectedMonthly, { currency: billingCurrency, decimals: 0 })}
              sub={kpisById.monthly_trend?.sub || null}
              tone="default"
              href="/costs"
              trendAmount={kpisById.monthly_trend?.delta_usd}
              currency={billingCurrency}
            />
          </div>
          <div
            className="dashboard-hero__metric-group dashboard-hero__metric-group--resources"
            role="group"
            aria-label="Resources and findings"
          >
            <HeroMetric
              label="Total resources"
              value={Number(totalResources).toLocaleString()}
              sub={kpisById.total_resources?.sub || null}
              tone="default"
            />
            <HeroMetric
              label="Open findings"
              value={Number(openFindings).toLocaleString()}
              tone={openFindings > 0 ? 'warning' : 'default'}
              href="/optimization-hub?tab=actions"
            />
            <HeroMetric
              label={`Est. savings/mo (${billingCurrency})`}
              value={formatCurrency(estSavings, { currency: billingCurrency, decimals: 0 })}
              tone="success"
              href="/optimization-hub?tab=actions"
            />
          </div>
        </div>
      </div>
      {primaryBudget && (
        <p className="dashboard-hero__budget-note">
          Budget: {formatCurrency(primaryBudget.amount, { currency: billingCurrency, decimals: 0 })}
          {' · '}
          Remaining: {formatCurrency(budgetRemaining, { currency: billingCurrency, decimals: 0 })}
        </p>
      )}
    </section>
  );
}
