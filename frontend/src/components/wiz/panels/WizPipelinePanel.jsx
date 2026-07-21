import React, { useContext, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Play, RefreshCw } from 'lucide-react';
import { AppCtx } from '../../../App';
import {
  fetchPipelineRouting,
  fetchPipelineStatus,
  triggerPipelineRun,
} from '../../../api/pipeline';
import AdminOnly from '../../AdminOnly';
import { LoadingState, QueryErrorState } from '../../QueryStates';
import { getErrorMessage } from '../../../api/errors';

const PIPELINE_FLOW = [
  { key: 'normalized', label: 'Cost sync' },
  { key: 'metrics_collected', label: 'Metrics' },
  { key: 'recommendations_ready', label: 'Analysis' },
];

const STAGE_LABELS = {
  normalized: 'Cost sync',
  pending: 'Pending',
  metrics_collected: 'Metrics collected',
  metrics_ready: 'Metrics collected',
  quality_scored: 'Data quality',
  recommendations_ready: 'Analysis ready',
  recommended: 'Analysis ready',
};

export default function WizPipelinePanel() {
  const { subscription } = useContext(AppCtx);
  const qc = useQueryClient();
  const [runError, setRunError] = useState('');

  const { data: routing } = useQuery({
    queryKey: ['pipeline-routing'],
    queryFn: fetchPipelineRouting,
    staleTime: 5 * 60_000,
  });

  const {
    data: status,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['pipeline-status', subscription],
    queryFn: () => fetchPipelineStatus(subscription),
    enabled: !!subscription,
    refetchInterval: 30_000,
  });

  const runMut = useMutation({
    mutationFn: () => triggerPipelineRun(subscription),
    onMutate: () => setRunError(''),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pipeline-status', subscription] });
    },
    onError: (err) => setRunError(getErrorMessage(err, 'Could not start pipeline run.')),
  });

  if (!subscription) {
    return (
      <div className="wiz-empty">
        <strong>Select a subscription</strong>
        Pipeline status is shown per subscription.
      </div>
    );
  }

  const subStatus = status?.subscriptions?.[subscription] || status?.subscriptions?.[subscription?.toLowerCase()];
  const stages = subStatus?.stage_counts || {};
  const latestRun = subStatus?.latest_run;
  const indexed = status?.indexed_assessment_files;

  const flowCounts = PIPELINE_FLOW.map((step) => ({
    ...step,
    count: stages[step.key] ?? 0,
  }));
  const totalResources = flowCounts.reduce((sum, step) => sum + step.count, 0) || 0;

  return (
    <div className="wiz-panel" id="wiz-panel-pipeline" role="tabpanel" aria-labelledby="wiz-tab-pipeline">
      {runError && (
        <div className="alert alert--danger" role="alert">{runError}</div>
      )}

      <section className="wiz-card">
        <header className="wiz-card__head">
          <h3>Assessment pipeline</h3>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              <RefreshCw size={14} />
              Refresh
            </button>
            <AdminOnly>
              <button
                type="button"
                className="btn btn-primary btn--sm"
                onClick={() => runMut.mutate()}
                disabled={runMut.isPending}
              >
                <Play size={14} />
                {runMut.isPending ? 'Running…' : 'Run pipeline'}
              </button>
            </AdminOnly>
          </div>
        </header>

        {isLoading && <LoadingState message="Loading pipeline status…" />}
        {isError && <QueryErrorState error={error} onRetry={refetch} />}

        {!isLoading && !isError && (
          <>
            <div className="hub-pipeline-strip__stages" role="list" aria-label="Pipeline flow">
              {flowCounts.map((step, index) => {
                const pct = totalResources > 0
                  ? Math.round((step.count / totalResources) * 100)
                  : 0;
                return (
                  <React.Fragment key={step.key}>
                    <div className="hub-pipeline-strip__stage" role="listitem">
                      <span className="hub-pipeline-strip__stage-label">{step.label}</span>
                      <strong>{step.count.toLocaleString()}</strong>
                      {totalResources > 0 && (
                        <span className="wiz-pill wiz-pill--muted">{pct}%</span>
                      )}
                    </div>
                    {index < flowCounts.length - 1 && (
                      <span className="hub-pipeline-strip__meta" aria-hidden>→</span>
                    )}
                  </React.Fragment>
                );
              })}
            </div>

            <div className="wiz-pipeline-stages">
              {Object.entries(STAGE_LABELS).map(([key, label]) => (
                stages[key] != null && (
                  <div key={key} className="wiz-stage">
                    <div className="wiz-stage__label">{label}</div>
                    <div className="wiz-stage__value">{(stages[key] ?? 0).toLocaleString()}</div>
                  </div>
                )
              ))}
              <div className="wiz-stage">
                <div className="wiz-stage__label">Assessment files</div>
                <div className="wiz-stage__value">{(indexed ?? '—').toLocaleString?.() ?? indexed}</div>
              </div>
            </div>

            {routing && (
              <div style={{ padding: '0 1rem 1rem' }}>
                <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.85rem' }}>Routing</h4>
                <div className="wiz-pill-row">
                  {routing.unified_recommendation_mode && (
                    <span className="wiz-pill wiz-pill--ok">Unified mode</span>
                  )}
                  {routing.integrated_sub_engines_enabled && (
                    <span className="wiz-pill wiz-pill--ok">Sub-engines on</span>
                  )}
                  {routing.assessment_pipeline_enabled && (
                    <span className="wiz-pill">Assessment pipeline</span>
                  )}
                </div>
              </div>
            )}

            {latestRun && (
              <div style={{ padding: '0 1rem 1rem', borderTop: '1px solid var(--border-subtle)' }}>
                <h4 style={{ margin: '0.75rem 0 0.5rem', fontSize: '0.85rem' }}>Latest run</h4>
                <div className="wiz-detail__meta-grid">
                  <div className="wiz-meta-item">
                    <label>Status</label>
                    <span>{latestRun.status}</span>
                  </div>
                  <div className="wiz-meta-item">
                    <label>Stage</label>
                    <span>{latestRun.current_stage || '—'}</span>
                  </div>
                  <div className="wiz-meta-item">
                    <label>Started</label>
                    <span>{latestRun.started_at || '—'}</span>
                  </div>
                  <div className="wiz-meta-item">
                    <label>Finished</label>
                    <span>{latestRun.finished_at || '—'}</span>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
