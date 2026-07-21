import React from 'react';
import { Link } from 'react-router-dom';
import { formatCurrency, formatIsoDate } from '../../utils/format';
import { azureFieldLabel } from '../../utils/costCurrency';
import { toDisplayText } from '../../utils/formatDisplay';
import { costTimeframeLabel } from '../../config/costTimeframes';
import AdminOnly from '../AdminOnly';
import FetchCostsButton from '../FetchCostsButton';

function HeroMetric({ label, value, sub, tone = 'default' }) {
  return (
    <div className={`dashboard-hero__metric dashboard-hero__metric--${tone}`}>
      <span className="dashboard-hero__metric-value">{value}</span>
      <span className="dashboard-hero__metric-label">{label}</span>
      {sub && <span className="dashboard-hero__metric-sub">{sub}</span>}
    </div>
  );
}

function HeroSkeleton() {
  return (
    <section className="dashboard-hero cost-explorer-hero dashboard-hero--loading" aria-busy="true">
      <div className="dashboard-hero__glow" aria-hidden />
      <div className="dashboard-hero__content">
        <div className="dashboard-hero__main">
          <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--sm" />
          <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--lg" />
          <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--md" />
        </div>
        <div className="dashboard-hero__metrics">
          {[1, 2, 3].map((i) => (
            <div key={i} className="dashboard-kpi-skeleton dashboard-kpi-skeleton--metric" />
          ))}
        </div>
      </div>
    </section>
  );
}

function truncateName(name, max) {
  if (!name || name.length <= max) return name;
  return `${name.slice(0, max - 1)}…`;
}

function dailySpanDays(mtdStart, mtdEnd) {
  if (!mtdStart || !mtdEnd) return 30;
  try {
    const start = new Date(`${mtdStart}T00:00:00`);
    const end = new Date(`${mtdEnd}T00:00:00`);
    const diff = Math.round((end - start) / (1000 * 60 * 60 * 24)) + 1;
    return Math.max(1, diff);
  } catch {
    return 30;
  }
}

export default function CostExplorerHero({
  subscriptionLabel,
  currency,
  timeframe,
  mtdStart,
  mtdEnd,
  total,
  topService,
  serviceCount,
  mtdPeriodLabel,
  lastSyncedAt,
  isLoading,
  onSync,
  syncing,
  canSync,
  compareTotal = null,
  comparePeriodLabel = null,
  periodDelta = null,
  periodDeltaPct = null,
  projectedMonthEnd = null,
}) {
  if (isLoading) {
    return <HeroSkeleton />;
  }

  const fieldLabel = azureFieldLabel(currency);
  const periodLabel = costTimeframeLabel(timeframe);
  const spanDays = dailySpanDays(mtdStart, mtdEnd);
  const avgDaily = total > 0 && spanDays ? total / spanDays : null;

  return (
    <section className="dashboard-hero cost-explorer-hero">
      <div className="dashboard-hero__glow" aria-hidden />
      <div className="dashboard-hero__content">
        <div className="dashboard-hero__main">
          <p className="dashboard-hero__eyebrow">Cost management</p>
          <h2 className="dashboard-hero__title">
            {subscriptionLabel ? toDisplayText(subscriptionLabel) : 'Cost explorer'}
          </h2>
          <p className="dashboard-hero__sub">
            {periodLabel}
            {mtdPeriodLabel ? ` · ${mtdPeriodLabel}` : ''}
            {` · ${fieldLabel}`}
            {lastSyncedAt ? ` · Synced ${formatIsoDate(lastSyncedAt.slice(0, 10))}` : ''}
          </p>
          <div className="dashboard-hero__actions">
            <Link to="/action-centre" className="btn btn-ghost btn-sm">Action centre</Link>
            {canSync && (
              <AdminOnly>
                <FetchCostsButton onClick={onSync} loading={syncing} />
              </AdminOnly>
            )}
          </div>
        </div>
        <div className="dashboard-hero__metrics">
          <HeroMetric
            label={`Period spend (${currency})`}
            value={formatCurrency(total, { currency, decimals: 0 })}
            sub={compareTotal != null && comparePeriodLabel
              ? `vs ${formatCurrency(compareTotal, { currency, decimals: 0 })} (${comparePeriodLabel})`
              : null}
            tone="default"
          />
          {periodDelta != null && (
            <HeroMetric
              label="Period change"
              value={`${periodDelta >= 0 ? '+' : ''}${formatCurrency(periodDelta, { currency, decimals: 0 })}`}
              sub={periodDeltaPct != null ? `${periodDeltaPct >= 0 ? '+' : ''}${periodDeltaPct.toFixed(1)}%` : null}
              tone={periodDelta > 0 ? 'warning' : 'success'}
            />
          )}
          <HeroMetric
            label="Top service"
            value={topService?.name ? truncateName(topService.name, 18) : '—'}
            sub={topService ? formatCurrency(topService.cost, { currency, decimals: 0 }) : null}
            tone="success"
          />
          <HeroMetric
            label="Services tracked"
            value={Number(serviceCount).toLocaleString()}
            sub={avgDaily ? `~${formatCurrency(avgDaily, { currency, decimals: 0 })}/day` : null}
            tone="default"
          />
        </div>
      </div>
      {projectedMonthEnd != null && (
        <p className={`cost-velocity-footer${compareTotal != null && projectedMonthEnd > compareTotal ? ' cost-velocity-footer--warn' : ''}`}>
          At this pace, month-end spend will be ~{formatCurrency(projectedMonthEnd, { currency, decimals: 0 })}
        </p>
      )}
    </section>
  );
}
