import React from 'react';
import { Link } from 'react-router-dom';
import { formatCurrency } from '../../utils/format';
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
    <section className="dashboard-hero resource-list-hero dashboard-hero--loading" aria-busy="true">
      <div className="dashboard-hero__glow" aria-hidden />
      <div className="dashboard-hero__content">
        <div className="dashboard-hero__main">
          <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--sm" />
          <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--lg" />
        </div>
        <div className="dashboard-hero__metrics">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="dashboard-kpi-skeleton dashboard-kpi-skeleton--metric" />
          ))}
        </div>
      </div>
    </section>
  );
}

export default function ResourceListHero({
  title,
  subscriptionLabel,
  filteredCount,
  totalCount,
  sourceLabel,
  resourcesWithFindings,
  openFindings,
  totalSavings,
  currency,
  isLive,
  isLoading,
}) {
  if (isLoading && totalCount === 0) {
    return <HeroSkeleton />;
  }

  return (
    <section className="dashboard-hero resource-list-hero">
      <div className="dashboard-hero__glow" aria-hidden />
      <div className="dashboard-hero__content">
        <div className="dashboard-hero__main">
          <p className="dashboard-hero__eyebrow">Resource inventory</p>
          <h2 className="dashboard-hero__title">{title}</h2>
          <p className="dashboard-hero__sub">
            {sourceLabel ? sourceLabel : 'Inventory'}
            {subscriptionLabel ? ` · ${toDisplayText(subscriptionLabel)}` : ''}
          </p>
          <div className="dashboard-hero__actions">
            <Link to="/action-centre" className="btn btn-ghost btn-sm">Action centre</Link>
            <Link to="/" className="btn btn-ghost btn-sm">Dashboard</Link>
            {isLive && (
              <span className="resource-list-hero__live-badge">Live preview</span>
            )}
          </div>
        </div>
        <div className="dashboard-hero__metrics">
          <HeroMetric
            label="In view"
            value={Number(filteredCount).toLocaleString()}
            tone="default"
          />
          <HeroMetric
            label="With findings"
            value={Number(resourcesWithFindings).toLocaleString()}
            tone={resourcesWithFindings > 0 ? 'warning' : 'default'}
          />
          <HeroMetric
            label="Open findings"
            value={Number(openFindings).toLocaleString()}
            tone={openFindings > 0 ? 'warning' : 'default'}
          />
          {totalSavings > 0 && (
            <HeroMetric
              label="Est. savings/mo"
              value={formatCurrency(totalSavings, { currency, decimals: 0 })}
              tone="success"
            />
          )}
        </div>
      </div>
    </section>
  );
}
