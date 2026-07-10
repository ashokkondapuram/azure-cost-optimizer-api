import React from 'react';
import { Link } from 'react-router-dom';
import { toDisplayText } from '../../utils/formatDisplay';
import SavingsScopeNote from '../savings/SavingsScopeNote';

export function HeroMetric({ label, value, tone = 'default', href, sub, featured = false }) {
  const content = (
    <div className={`dashboard-hero__metric dashboard-hero__metric--${tone}${featured ? ' dashboard-hero__metric--featured' : ''}`}>
      <span className="dashboard-hero__metric-value">{value}</span>
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

export function HeroSkeleton({ variant = '', metricCount = 4 }) {
  return (
    <section className={`dashboard-hero ${variant} dashboard-hero--loading`} aria-busy="true">
      <div className="dashboard-hero__glow" aria-hidden />
      <div className="dashboard-hero__content">
        <div className="dashboard-hero__main">
          <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--sm" />
          <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--lg" />
        </div>
        <div className="dashboard-hero__metrics">
          {Array.from({ length: metricCount }, (_, i) => (
            <div key={i} className="dashboard-kpi-skeleton dashboard-kpi-skeleton--metric" />
          ))}
        </div>
      </div>
    </section>
  );
}

/**
 * Shared gradient hero band used across dashboard, settings, admin, and list pages.
 */
export default function PageHero({
  variant = '',
  eyebrow,
  title,
  subtitle,
  scopeNote,
  metrics = [],
  actions = [],
  footer,
  isLoading = false,
  skeletonMetrics = 4,
  embedded = false,
  children,
}) {
  if (isLoading) {
    return <HeroSkeleton variant={variant} metricCount={skeletonMetrics} />;
  }

  return (
    <section className={`dashboard-hero page-hero ${variant}${embedded ? ' page-hero--embedded' : ''}`.trim()}>
      <div className="dashboard-hero__glow" aria-hidden />
      <div className="dashboard-hero__content">
        <div className="dashboard-hero__main">
          {!embedded && eyebrow && <p className="dashboard-hero__eyebrow">{eyebrow}</p>}
          {!embedded && title && <h2 className="dashboard-hero__title">{toDisplayText(title)}</h2>}
          {!embedded && subtitle && <p className="dashboard-hero__sub">{subtitle}</p>}
          {scopeNote && (
            <SavingsScopeNote
              title={scopeNote.title}
              description={scopeNote.description}
              className={`page-hero__scope-note${embedded ? ' page-hero__scope-note--embedded' : ''}`}
            />
          )}
          {(actions.length > 0 || children) && (
            <div className="dashboard-hero__actions">
              {actions.map((action) => {
                if (action.href) {
                  return (
                    <Link
                      key={action.id || action.label}
                      to={action.href}
                      className={`btn btn-sm ${action.primary ? 'btn-primary' : 'btn-ghost'}`}
                    >
                      {action.icon}
                      {action.label}
                    </Link>
                  );
                }
                if (action.onClick) {
                  return (
                    <button
                      key={action.id || action.label}
                      type="button"
                      className={`btn btn-sm ${action.primary ? 'btn-primary' : 'btn-ghost'}`}
                      onClick={action.onClick}
                      disabled={action.disabled}
                    >
                      {action.icon}
                      {action.label}
                    </button>
                  );
                }
                return null;
              })}
              {children}
            </div>
          )}
        </div>
        {metrics.length > 0 && (
          <div className="dashboard-hero__metrics">
            {metrics.map((m) => (
              <HeroMetric key={m.label} {...m} />
            ))}
          </div>
        )}
      </div>
      {footer}
    </section>
  );
}
