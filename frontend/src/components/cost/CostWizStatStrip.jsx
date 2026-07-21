import React from 'react';
import { DollarSign, TrendingUp, Layers, Calendar } from 'lucide-react';
import { formatCurrency } from '../../utils/format';

function WizStat({ label, value, sub, tone = 'default', icon: Icon }) {
  return (
    <div className="wiz-stat">
      <span className={`wiz-stat__icon wiz-stat__icon--${tone}`} aria-hidden>
        <Icon size={16} />
      </span>
      <span>
        <span className="wiz-stat__label">{label}</span>
        <strong className="wiz-stat__value">{value}</strong>
        {sub && <span className="wiz-stat__sub">{sub}</span>}
      </span>
    </div>
  );
}

export default function CostWizStatStrip({
  currency,
  total,
  compareTotal,
  comparePeriodLabel,
  periodDelta,
  periodDeltaPct,
  topService,
  serviceCount,
  avgDaily,
  projectedMonthEnd,
  isLoading,
}) {
  if (isLoading) {
    return (
      <div className="wiz-stat-strip" aria-busy="true">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="wiz-stat dashboard-kpi-skeleton dashboard-kpi-skeleton--metric" />
        ))}
      </div>
    );
  }

  return (
    <div className="wiz-stat-strip cost-wiz-stat-strip" aria-label="Cost metrics">
      <WizStat
        label={`Period spend (${currency})`}
        value={formatCurrency(total, { currency, decimals: 0 })}
        sub={compareTotal != null && comparePeriodLabel
          ? `vs ${formatCurrency(compareTotal, { currency, decimals: 0 })} (${comparePeriodLabel})`
          : 'Selected period total'}
        tone="info"
        icon={DollarSign}
      />
      {periodDelta != null && (
        <WizStat
          label="Period change"
          value={`${periodDelta >= 0 ? '+' : ''}${formatCurrency(periodDelta, { currency, decimals: 0 })}`}
          sub={periodDeltaPct != null ? `${periodDeltaPct >= 0 ? '+' : ''}${periodDeltaPct.toFixed(1)}%` : null}
          tone={periodDelta > 0 ? 'critical' : 'success'}
          icon={TrendingUp}
        />
      )}
      <WizStat
        label="Top service"
        value={topService?.name ? (topService.name.length > 20 ? `${topService.name.slice(0, 19)}…` : topService.name) : '—'}
        sub={topService ? formatCurrency(topService.cost, { currency, decimals: 0 }) : 'No service data'}
        tone="success"
        icon={Layers}
      />
      <WizStat
        label="Services"
        value={Number(serviceCount).toLocaleString()}
        sub={avgDaily ? `~${formatCurrency(avgDaily, { currency, decimals: 0 })}/day` : 'Tracked in period'}
        tone="default"
        icon={Layers}
      />
      {projectedMonthEnd != null && (
        <WizStat
          label="Projected month-end"
          value={formatCurrency(projectedMonthEnd, { currency, decimals: 0 })}
          sub="At current daily pace"
          tone="warning"
          icon={Calendar}
        />
      )}
    </div>
  );
}
