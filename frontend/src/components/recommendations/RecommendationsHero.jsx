import React from 'react';
import { Link } from 'react-router-dom';
import { formatCurrency } from '../../utils/format';
import { resolveBillingCurrency } from '../../utils/costCurrency';
import { toDisplayText } from '../../utils/formatDisplay';

function HeroMetric({ label, value, tone = 'default' }) {
  return (
    <div className={`dashboard-hero__metric dashboard-hero__metric--${tone}`}>
      <span className="dashboard-hero__metric-value">{value}</span>
      <span className="dashboard-hero__metric-label">{label}</span>
    </div>
  );
}

function HeroSkeleton() {
  return (
    <section className="dashboard-hero recommendations-hero dashboard-hero--loading" aria-busy="true">
      <div className="dashboard-hero__glow" aria-hidden />
      <div className="dashboard-hero__content">
        <div className="dashboard-hero__main">
          <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--sm" />
          <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--lg" />
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

export default function RecommendationsHero({
  subscriptionLabel,
  summary,
  filteredCount,
  filteredSavings,
  currency,
  isLoading,
}) {
  if (isLoading && !summary) {
    return <HeroSkeleton />;
  }

  const openFindings = summary?.open_findings ?? 0;
  const totalSavings = summary?.total_estimated_savings_usd ?? 0;
  const costCount = summary?.cost_optimization_findings ?? summary?.with_savings_findings ?? 0;
  const govCount = summary?.governance_findings ?? 0;
  const displayCurrency = resolveBillingCurrency(currency);

  return (
    <section className="dashboard-hero recommendations-hero">
      <div className="dashboard-hero__glow" aria-hidden />
      <div className="dashboard-hero__content">
        <div className="dashboard-hero__main">
          <p className="dashboard-hero__eyebrow">Optimization</p>
          <h2 className="dashboard-hero__title">
            {subscriptionLabel ? toDisplayText(subscriptionLabel) : 'Action centre'}
          </h2>
          <p className="dashboard-hero__sub">
            {filteredCount.toLocaleString()} showing
            {summary ? ` · ${openFindings.toLocaleString()} open` : ''}
          </p>
          <div className="dashboard-hero__actions">
            <Link to="/" className="btn btn-ghost btn-sm">Dashboard</Link>
            <Link to="/costs" className="btn btn-ghost btn-sm">Cost explorer</Link>
            <Link to="/history" className="btn btn-ghost btn-sm">Run history</Link>
          </div>
        </div>
        <div className="dashboard-hero__metrics">
          <HeroMetric
            label="Open findings"
            value={Number(openFindings).toLocaleString()}
            tone={openFindings > 0 ? 'warning' : 'default'}
          />
          <HeroMetric
            label={`Est. savings/mo (${displayCurrency})`}
            value={formatCurrency(totalSavings, { currency: displayCurrency, decimals: 0 })}
            tone="success"
          />
          <HeroMetric
            label={`Filtered savings (${displayCurrency})`}
            value={formatCurrency(filteredSavings, { currency: displayCurrency, decimals: 0 })}
            tone="default"
          />
          <HeroMetric
            label="Cost · Governance"
            value={`${Number(costCount).toLocaleString()} · ${Number(govCount).toLocaleString()}`}
            tone="default"
          />
        </div>
      </div>
    </section>
  );
}
