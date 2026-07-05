import React, { useContext } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Gauge, ArrowRight } from 'lucide-react';
import { AppCtx } from '../../App';
import { fetchOptimizationTrends } from '../../api/azure';
import { formatCurrency } from '../../utils/format';
import { formatScore } from '../../utils/scoreboardUtils';

function TrendsSkeleton() {
  return (
    <section className="dashboard-opt-trends dashboard-opt-trends--loading" aria-busy="true">
      <div className="dashboard-opt-trends__glow" aria-hidden />
      <div className="dashboard-opt-trends__content">
        <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--sm" />
        <div className="dashboard-opt-trends__metrics">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="dashboard-kpi-skeleton dashboard-kpi-skeleton--metric" />
          ))}
        </div>
      </div>
    </section>
  );
}

export default function DashboardOptimizationTrends() {
  const { subscription, billingCurrency } = useContext(AppCtx);

  const { data, isPending } = useQuery({
    queryKey: ['optimization-trends', subscription],
    queryFn: () => fetchOptimizationTrends({ subscription_id: subscription }),
    enabled: Boolean(subscription),
    staleTime: 120_000,
    placeholderData: keepPreviousData,
  });

  if (!subscription) return null;
  if (isPending && !data) return <TrendsSkeleton />;

  const currency = billingCurrency || 'CAD';
  const resourcesScored = data?.resources_scored ?? 0;
  const tier1 = data?.tier_counts?.tier1_safe ?? 0;
  const avgScore = data?.scoring?.average_score;
  const hasScoring = resourcesScored > 0;

  return (
    <section className="dashboard-opt-trends" aria-label="Advanced optimization">
      <div className="dashboard-opt-trends__glow" aria-hidden />
      <div className="dashboard-opt-trends__content">
        <div className="dashboard-opt-trends__intro">
          <div className="dashboard-opt-trends__title-row">
            <span className="dashboard-opt-trends__icon" aria-hidden>
              <Gauge size={20} strokeWidth={2} />
            </span>
            <div>
              <p className="dashboard-opt-trends__eyebrow">Optimization engine</p>
              <h3 className="dashboard-opt-trends__title">Advanced optimization</h3>
            </div>
          </div>
          <div className="dashboard-opt-trends__actions">
            <Link to="/optimization-hub?tab=actions" className="btn btn--ghost btn--sm">
              Actions
            </Link>
            <Link to="/optimization-hub" className="btn btn-secondary btn-sm">
              Optimization hub <ArrowRight size={14} />
            </Link>
          </div>
        </div>

        {!hasScoring ? (
          <div className="dashboard-opt-trends__empty">
            <p>No resources scored yet. Run advanced scoring to see tier breakdown and savings potential.</p>
            <Link to="/admin/optimization" className="btn btn-secondary btn-sm">
              Open sync center
            </Link>
          </div>
        ) : (
          <div className="dashboard-opt-trends__metrics">
            <div className="dashboard-opt-trends__metric dashboard-opt-trends__metric--primary">
              <span className="dashboard-opt-trends__value">{resourcesScored.toLocaleString()}</span>
              <span className="dashboard-opt-trends__label">Resources scored</span>
            </div>
            <div className="dashboard-opt-trends__metric">
              <span className="dashboard-opt-trends__value">{tier1.toLocaleString()}</span>
              <span className="dashboard-opt-trends__label">Tier 1 safe</span>
            </div>
            <div className="dashboard-opt-trends__metric dashboard-opt-trends__metric--savings">
              <span className="dashboard-opt-trends__value">
                {formatCurrency(data.total_estimated_monthly_savings || 0, { currency, decimals: 0 })}
              </span>
              <span className="dashboard-opt-trends__label">Est. savings/mo</span>
            </div>
            <div className="dashboard-opt-trends__metric">
              <span className="dashboard-opt-trends__value">
                {avgScore != null ? formatScore(avgScore) : '—'}
              </span>
              <span className="dashboard-opt-trends__label">Avg score</span>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
