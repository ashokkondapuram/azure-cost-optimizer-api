import React, { useContext, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AppCtx } from '../App';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';
import PageHeader from '../components/PageHeader';
import PageHero from '../components/layout/PageHero';
import FilterBar from '../components/FilterBar';
import AdminOnly from '../components/AdminOnly';
import useRolloutStages from '../hooks/useRolloutStages';
import {
  expandRolloutStage,
  observeRolloutStages,
  planOptimizationRollout,
  rollbackRolloutStage,
  startRolloutStage,
} from '../api/azure';
import { getErrorMessage } from '../api/errors';
import { rolloutStatusLabel, rolloutTierLabel, observationProgress } from '../utils/rolloutUtils';
import { tierTone, tierLabel } from '../utils/scoreboardUtils';
import {
  LoadingState, SubscriptionRequired, EmptyState, QueryErrorState,
} from '../components/QueryStates';
import { PAGE_ICONS } from '../config/assetIcons';
import { RefreshCw, Play, CheckCircle, RotateCcw } from 'lucide-react';

const STATUS_OPTIONS = ['proposed', 'in_progress', 'completed', 'rolled_back'];

export default function RolloutMonitor({ embedded = false }) {
  const { subscription } = useContext(AppCtx);
  const { isAdmin } = useAuth();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');
  const [rollbackStage, setRollbackStage] = useState(null);
  const [rollbackReason, setRollbackReason] = useState('');

  const filters = useMemo(() => ({
    ...(statusFilter ? { status: statusFilter } : {}),
  }), [statusFilter]);

  const {
    items, statusSummary, isLoading, isError, error, refetch, indexReady,
  } = useRolloutStages(subscription, filters);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['rollout-stages'] });
    queryClient.invalidateQueries({ queryKey: ['optimization-trends'] });
  };

  const planMutation = useMutation({
    mutationFn: () => planOptimizationRollout({ subscription_id: subscription, replace_existing: true }),
    onSuccess: (data) => {
      invalidate();
      toast.success(`Created ${data.stages_created || 0} rollout stages`);
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  });

  const observeMutation = useMutation({
    mutationFn: () => observeRolloutStages({ subscription_id: subscription }),
    onSuccess: (data) => {
      invalidate();
      const ready = data.ready_to_expand?.length || 0;
      const rollback = data.needs_rollback?.length || 0;
      toast.success(`Observation check: ${ready} ready, ${rollback} need rollback`);
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  });

  const startMutation = useMutation({
    mutationFn: (stageId) => startRolloutStage(stageId, subscription),
    onSuccess: () => { invalidate(); toast.success('Stage started'); },
    onError: (err) => toast.error(getErrorMessage(err)),
  });

  const expandMutation = useMutation({
    mutationFn: ({ stageId, force }) => expandRolloutStage(stageId, subscription, force),
    onSuccess: () => { invalidate(); toast.success('Stage completed'); },
    onError: (err) => toast.error(getErrorMessage(err)),
  });

  const rollbackMutation = useMutation({
    mutationFn: ({ stageId, reason }) => rollbackRolloutStage(stageId, subscription, reason),
    onSuccess: () => {
      invalidate();
      setRollbackStage(null);
      setRollbackReason('');
      toast.success('Stage rolled back');
    },
    onError: (err) => toast.error(getErrorMessage(err)),
  });

  if (!subscription) return <SubscriptionRequired />;

  return (
    <div className={`page rollout-monitor-page${embedded ? ' optimization-hub-panel__content' : ''}`}>
      {!embedded && (
      <PageHeader
        title="Rollout monitor"
        subtitle="Track staged optimization rollouts and observation windows"
        iconKey={PAGE_ICONS.rollout || 'optimization'}
        actions={(
          <AdminOnly>
            <button type="button" className="btn btn--secondary btn--sm" disabled={planMutation.isPending} onClick={() => planMutation.mutate()}>
              Plan rollout
            </button>
            <button type="button" className="btn btn--ghost btn--sm" disabled={observeMutation.isPending} onClick={() => observeMutation.mutate()}>
              <RefreshCw size={14} className={observeMutation.isPending ? 'spin' : ''} />
              Check observation
            </button>
          </AdminOnly>
        )}
      />
      )}

      <PageHero
        variant="rollout-hero"
        eyebrow="Rollout orchestration"
        title="Rollout monitor"
        subtitle="Track staged rollouts, observation windows, and expansion readiness after actions are approved."
        isLoading={isLoading && !items.length}
        metrics={[
          {
            label: 'Stages',
            value: items.length.toLocaleString(),
            tone: 'default',
          },
          {
            label: 'In progress',
            value: (statusSummary.in_progress || 0).toLocaleString(),
            tone: 'warning',
          },
          {
            label: 'Completed',
            value: (statusSummary.completed || 0).toLocaleString(),
            tone: 'success',
          },
          {
            label: 'Rolled back',
            value: (statusSummary.rolled_back || 0).toLocaleString(),
            tone: (statusSummary.rolled_back || 0) > 0 ? 'danger' : 'default',
          },
        ]}
        actions={isAdmin ? [
          {
            id: 'plan',
            label: planMutation.isPending ? 'Planning…' : 'Plan rollout',
            onClick: () => planMutation.mutate(),
            disabled: planMutation.isPending,
            primary: true,
          },
          {
            id: 'observe',
            label: 'Check observation',
            onClick: () => observeMutation.mutate(),
            disabled: observeMutation.isPending,
            icon: <RefreshCw size={14} className={observeMutation.isPending ? 'spin' : ''} />,
          },
        ] : []}
      />

      <FilterBar>
        <select className="filter-select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>{rolloutStatusLabel(s)}</option>
          ))}
        </select>
        <Link to="/optimization-hub?tab=scoreboard" className="btn btn--ghost btn--sm">View scoreboard</Link>
      </FilterBar>

      {isLoading && <LoadingState message="Loading rollout stages…" />}
      {isError && <QueryErrorState error={error} onRetry={refetch} />}
      {indexReady && !items.length && (
        <EmptyState
          title="No rollout stages"
          message="Run advanced scoring, approve actions, then plan a rollout."
        />
      )}

      {items.length > 0 && (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Tier</th>
                <th>Resources</th>
                <th>Status</th>
                <th>Observation</th>
                <th>Progress</th>
                {isAdmin && <th>Actions</th>}
              </tr>
            </thead>
            <tbody>
              {items.map((stage) => {
                const obs = observationProgress(stage);
                return (
                  <tr key={stage.id}>
                    <td>
                      <span className={`tier-pill tier-pill--${tierTone(stage.stage_tier)}`}>
                        {rolloutTierLabel(stage.stage_tier)}
                      </span>
                    </td>
                    <td>{stage.resources_in_stage}</td>
                    <td>{rolloutStatusLabel(stage.status)}</td>
                    <td>{obs.label}</td>
                    <td>
                      <span className="observation-bar" aria-hidden>
                        <span className="observation-bar__fill" style={{ width: `${obs.pct}%` }} />
                      </span>
                    </td>
                    {isAdmin && (
                      <td className="rollout-actions-cell">
                        {stage.status === 'proposed' && (
                          <button type="button" className="btn btn--ghost btn--sm" title="Start" onClick={() => startMutation.mutate(stage.id)}>
                            <Play size={14} />
                          </button>
                        )}
                        {stage.status === 'in_progress' && (
                          <>
                            <button
                              type="button"
                              className="btn btn--ghost btn--sm"
                              title="Complete"
                              onClick={() => expandMutation.mutate({ stageId: stage.id, force: stage.observation_window_days === 0 })}
                            >
                              <CheckCircle size={14} />
                            </button>
                            <button type="button" className="btn btn--ghost btn--sm" title="Rollback" onClick={() => setRollbackStage(stage)}>
                              <RotateCcw size={14} />
                            </button>
                          </>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {rollbackStage && (
        <div className="modal-overlay" role="presentation" onClick={() => setRollbackStage(null)}>
          <div className="modal-card" role="dialog" onClick={(e) => e.stopPropagation()}>
            <div className="modal-card__header">
              <h2>Rollback stage</h2>
              <button type="button" className="btn-icon" onClick={() => setRollbackStage(null)}>×</button>
            </div>
            <div className="modal-card__body">
              <p>Roll back {tierLabel(rollbackStage.stage_tier)} stage with {rollbackStage.resources_in_stage} resources?</p>
              <label className="form-field">
                <span className="form-label">Reason</span>
                <textarea className="form-textarea" rows={3} value={rollbackReason} onChange={(e) => setRollbackReason(e.target.value)} />
              </label>
            </div>
            <div className="modal-card__footer">
              <button type="button" className="btn btn--ghost" onClick={() => setRollbackStage(null)}>Cancel</button>
              <button
                type="button"
                className="btn btn--primary"
                disabled={rollbackReason.trim().length < 3 || rollbackMutation.isPending}
                onClick={() => rollbackMutation.mutate({ stageId: rollbackStage.id, reason: rollbackReason.trim() })}
              >
                Rollback
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
