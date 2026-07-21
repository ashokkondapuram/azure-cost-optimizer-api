import React from 'react';
import { Link } from 'react-router-dom';
import { DollarSign, Layers } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { formatCurrency, formatDateRange } from '../../utils/format';
import { resolveDashboardBillingCurrency, resolveDashboardMtdAmount } from '../../utils/costCurrency';
import TrendBadge from '../visual/TrendBadge';
import Card from '../Card';

function WizStat({ label, value, sub, tone = 'default', icon: Icon, href, trendAmount, currency }) {
  const cardTone = tone === 'info' ? 'actions' : 'default';
  const inner = (
    <>
      <span className={`wiz-stat__icon wiz-stat__icon--${tone}`} aria-hidden>
        <Icon size={16} />
      </span>
      <span>
        <span className="wiz-stat__label type-label">{label}</span>
        <strong className="wiz-stat__value trend-indicator">{value}</strong>
        {sub && <span className="wiz-stat__sub type-body-small">{sub}</span>}
        {trendAmount != null && Number(trendAmount) !== 0 && (
          <TrendBadge deltaAmount={trendAmount} currency={currency} invert />
        )}
      </span>
    </>
  );

  if (href) {
    return (
      <Card as={Link} to={href} tone={cardTone} clickable className="wiz-stat wiz-stat--clickable">
        {inner}
      </Card>
    );
  }
  return <Card tone={cardTone} className="wiz-stat">{inner}</Card>;
}

function HeroSkeleton() {
  return (
    <div className="wiz-stat-strip dashboard-wiz-stat-strip" aria-busy="true">
      {Array.from({ length: 2 }, (_, i) => (
        <div key={i} className="wiz-stat dashboard-kpi-skeleton dashboard-kpi-skeleton--metric" />
      ))}
    </div>
  );
}

/**
 * Compact subscription metrics for the dashboard hero.
 * Findings summary and charts live in DashboardFindingsInsights; cost detail in Cost explorer.
 */
export default function DashboardWizStatStrip({
  portal,
  costSummary,
  costSync,
  currency,
  isLoading,
  costPeriodLabel,
  costPeriod = 'MonthToDate',
  resourceTypeFilterActive = false,
}) {
  const { isSuperuser } = useAuth();
  if (isLoading && !portal) {
    return <HeroSkeleton />;
  }
  if (!portal) return null;

  const billingCurrency = resolveDashboardBillingCurrency(costSummary, costSync, currency || 'CAD');
  const mtdAmount = resolveDashboardMtdAmount(costSummary, costSync);

  const kpisById = Object.fromEntries((portal.kpis || []).map((k) => [k.id, k]));
  const totalResources = kpisById.total_resources?.value ?? 0;
  const mtdDelta = portal.hero_deltas?.mtd_delta_usd ?? kpisById.monthly_trend?.mtd_delta_usd;

  const periodStart = costSummary?.period_start || costSummary?.mtd_start;
  const periodEnd = costSummary?.period_end || costSummary?.mtd_end;
  const mtdDateRangeLabel = periodStart && periodEnd
    ? formatDateRange(periodStart, periodEnd)
    : null;

  const mtdLabel = costPeriodLabel
    ? `Spend · ${costPeriodLabel}`
    : 'Spend this period';

  return (
    <div className="wiz-stat-strip dashboard-wiz-stat-strip" aria-label="Subscription metrics">
      <WizStat
        label={mtdLabel}
        value={formatCurrency(mtdAmount, { currency: billingCurrency, decimals: 0 })}
        sub={mtdDateRangeLabel || (resourceTypeFilterActive ? 'Selected types only' : billingCurrency)}
        tone="info"
        icon={DollarSign}
        href={`/costs?timeframe=${encodeURIComponent(costPeriod)}`}
        trendAmount={mtdDelta}
        currency={billingCurrency}
      />
      <WizStat
        label="Billed resources"
        value={Number(totalResources).toLocaleString()}
        sub={kpisById.total_resources?.sub || 'Synced inventory'}
        tone="default"
        icon={Layers}
        href={isSuperuser ? '/explorer' : '/action-centre'}
      />
    </div>
  );
}
