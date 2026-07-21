import React, { useContext } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ArrowRight, CheckCircle2, Layers, Zap } from 'lucide-react';
import { AppCtx } from '../../App';
import { fetchOptimizationTrends } from '../../api/azure';
import { QueryErrorState } from '../QueryStates';

function PipelineStat({ label, value, sub, tone = 'default', icon: Icon }) {
  return (
    <div className={`wiz-stat dashboard-pipeline-stat dashboard-pipeline-stat--${tone}`}>
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

function TrendsSkeleton() {
  return (
    <section className="dashboard-workflow-strip dashboard-workflow-strip--loading" aria-busy="true">
      <div className="dashboard-kpi-skeleton dashboard-kpi-skeleton--sm skeleton" />
      <div className="wiz-stat-strip dashboard-pipeline-stat-strip">
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="wiz-stat dashboard-kpi-skeleton dashboard-kpi-skeleton--metric" />
        ))}
      </div>
    </section>
  );
}

/** Optimization pipeline — compact workflow KPI strip. */
export default function DashboardOptimizationTrends() {
  const { subscription } = useContext(AppCtx);

  const { data, isPending, isError, error, refetch } = useQuery({
    queryKey: ['optimization-trends', subscription],
    queryFn: () => fetchOptimizationTrends({ subscription_id: subscription }),
    enabled: Boolean(subscription),
    staleTime: 120_000,
    placeholderData: keepPreviousData,
  });

  const pipelineByStatus = data?.pipeline_actions_by_status || data?.actions_by_status || {};
  const proposed = pipelineByStatus.proposed ?? 0;
  const approved = pipelineByStatus.approved ?? 0;
  const executed = pipelineByStatus.executed
    ?? data?.actions_by_status?.executed
    ?? data?.executed_actions
    ?? 0;

  if (!subscription) return null;
  if (isPending && !data) return <TrendsSkeleton />;
  if (isError && !data) {
    return (
      <QueryErrorState
        error={error}
        onRetry={refetch}
        title="Could not load action workflow"
      />
    );
  }

  return (
    <section className="dashboard-workflow-strip" aria-label="Action workflow">
      <header className="dashboard-workflow-strip__head">
        <h3 className="dashboard-section__title dashboard-section__title--bar">Action workflow</h3>
        <Link to="/action-centre" className="btn btn-ghost btn-sm">
          Action centre
          <ArrowRight size={14} />
        </Link>
      </header>

      <div className="wiz-stat-strip dashboard-pipeline-stat-strip" aria-label="Pipeline metrics">
        <PipelineStat
          label="Proposed"
          value={proposed.toLocaleString()}
          sub="Awaiting review"
          tone="warning"
          icon={Zap}
        />
        <PipelineStat
          label="Approved"
          value={approved.toLocaleString()}
          sub="Ready to execute"
          tone="info"
          icon={CheckCircle2}
        />
        <PipelineStat
          label="Executed"
          value={executed.toLocaleString()}
          sub="Completed"
          tone="success"
          icon={Layers}
        />
      </div>
    </section>
  );
}
