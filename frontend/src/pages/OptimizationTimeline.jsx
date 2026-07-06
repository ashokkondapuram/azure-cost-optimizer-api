import React, { useState, useContext } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity, Filter, CheckCircle2, XCircle, Clock, AlertTriangle, Zap, User, RefreshCw } from 'lucide-react';
import { AppCtx } from '../App';
import PageHeader from '../components/PageHeader';
import { SubscriptionRequired, LoadingState, ErrorState } from '../components/QueryStates';
import { fetchOptimizationActions, fetchFindings } from '../api/azure';

const TYPE_LABELS = {
  action_executed: 'Action Executed',
  action_rejected: 'Action Rejected',
  action_pending:  'Action Pending',
  action_approved: 'Action Approved',
  finding_open:    'Finding Open',
  finding_resolved:'Finding Resolved',
  finding_ignored: 'Finding Ignored',
  drift_detected:  'Drift Detected',
  other:           'Event',
};

function typeIcon(type) {
  if (type === 'action_executed' || type === 'finding_resolved') return <CheckCircle2 size={14} className="text-success" />;
  if (type === 'action_rejected' || type === 'finding_ignored')  return <XCircle size={14} className="text-danger" />;
  if (type === 'finding_open')    return <AlertTriangle size={14} className="text-warning" />;
  if (type === 'drift_detected')  return <Zap size={14} className="text-warning" />;
  if (type === 'action_pending' || type === 'action_approved')   return <Clock size={14} className="text-primary" />;
  return <Activity size={14} className="text-muted" />;
}

/** Normalise an optimization action record → timeline event */
export function actionToEvent(a) {
  const status = (a.status || '').toLowerCase();
  let type = 'other';
  if (status === 'executed' || status === 'completed')   type = 'action_executed';
  else if (status === 'rejected' || status === 'failed') type = 'action_rejected';
  else if (status === 'approved')                        type = 'action_approved';
  else if (status === 'pending')                         type = 'action_pending';
  return {
    id:       `action-${a.id || a.action_id}`,
    ts:       a.updated_at || a.executed_at || a.created_at || '—',
    actor:    a.assigned_to || a.executed_by || 'system',
    type,
    resource: a.resource_name || a.resource_id || '—',
    detail:   a.title || a.description || a.action_type || '—',
    outcome:  status === 'executed' || status === 'completed' ? 'success'
              : status === 'rejected' || status === 'failed'  ? 'warning'
              : 'info',
    savings:  Number(a.estimated_savings || 0) || null,
  };
}

/** Normalise a finding record → timeline event */
export function findingToEvent(f) {
  const status = (f.status || '').toLowerCase();
  let type = 'finding_open';
  if (status === 'resolved')                               type = 'finding_resolved';
  else if (status === 'ignored' || status === 'dismissed') type = 'finding_ignored';
  return {
    id:       `finding-${f.id || f.finding_id}`,
    ts:       f.updated_at || f.created_at || '—',
    actor:    f.updated_by || 'system',
    type,
    resource: f.resource_name || f.resource_id || '—',
    detail:   f.title || f.description || '—',
    outcome:  status === 'resolved' ? 'success'
              : (status === 'ignored' || status === 'dismissed') ? 'warning'
              : 'info',
    savings:  Number(f.estimated_monthly_savings || f.savings || 0) || null,
  };
}

export default function OptimizationTimeline() {
  const { subscription }    = useContext(AppCtx);
  const [typeFilter, setTypeFilter] = useState('all');

  const { data: actions = [], isLoading: la, isError: ea, refetch: ra } = useQuery({
    queryKey: ['timeline-actions', subscription],
    queryFn:  () => fetchOptimizationActions({ subscription_id: subscription, limit: 200 }),
    enabled:  !!subscription,
    staleTime: 3 * 60_000,
    select: data => Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : [],
  });

  const { data: findings = [], isLoading: lf, isError: ef, refetch: rf } = useQuery({
    queryKey: ['timeline-findings', subscription],
    queryFn:  () => fetchFindings({ subscription_id: subscription, limit: 200 }),
    enabled:  !!subscription,
    staleTime: 3 * 60_000,
    select: data => Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : [],
  });

  const isLoading = la || lf;
  const isError   = ea || ef;

  const events = React.useMemo(() => [
    ...actions .map(actionToEvent),
    ...findings.map(findingToEvent),
  ].sort((a, b) => {
    if (a.ts < b.ts) return 1;
    if (a.ts > b.ts) return -1;
    return 0;
  }), [actions, findings]);

  const types    = ['all', ...new Set(events.map(e => e.type))];
  const filtered = typeFilter === 'all' ? events : events.filter(e => e.type === typeFilter);
  const refetch  = () => { ra(); rf(); };

  return (
    <div className="page-shell opt-timeline-page">
      <PageHeader title="Optimization Timeline" subtitle="Unified audit trail of findings, actions, and automated events">
        <button className="btn btn-sm btn-ghost" onClick={refetch} title="Refresh"><RefreshCw size={13} /> Refresh</button>
      </PageHeader>

      {!subscription && <SubscriptionRequired />}
      {subscription && isLoading && <LoadingState message="Loading timeline…" />}
      {subscription && isError   && <ErrorState message="Failed to load timeline data." />}
      {subscription && !isLoading && !isError && (
        <>
          <div className="toolbar" style={{ marginBottom: '1rem', flexWrap: 'wrap' }}>
            <Filter size={13} className="text-muted" />
            {types.map(t => (
              <button key={t} className={`chip${typeFilter===t?' active':''}`} onClick={() => setTypeFilter(t)}>
                {t === 'all' ? 'All events' : (TYPE_LABELS[t] || t)}
              </button>
            ))}
          </div>

          {filtered.length === 0 ? (
            <div className="empty-state" style={{ padding: '2rem' }}>
              <Activity size={28} />
              <p>
                {events.length === 0
                  ? 'No findings or actions yet. Run an analysis to populate the timeline.'
                  : 'No events match the selected filter.'}
              </p>
            </div>
          ) : (
            <div className="timeline">
              {filtered.map((e, i) => (
                <div key={e.id} className={`timeline-item timeline-item--${e.outcome}`}>
                  <div className="timeline-item__dot">{typeIcon(e.type)}</div>
                  {i < filtered.length - 1 && <div className="timeline-item__line" />}
                  <div className="timeline-item__body">
                    <div className="timeline-item__head">
                      <span className="timeline-item__type">{TYPE_LABELS[e.type] || e.type}</span>
                      <span className="timeline-item__ts">{e.ts}</span>
                    </div>
                    <div className="timeline-item__resource"><code>{e.resource}</code></div>
                    <div className="timeline-item__detail">{e.detail}</div>
                    <div className="timeline-item__footer">
                      <span className="icon-inline" style={{ fontSize: '0.72rem', color: 'var(--text3)' }}>
                        <User size={11} /> {e.actor}
                      </span>
                      {e.savings > 0 && (
                        <span className="text-success" style={{ fontSize: '0.72rem', fontWeight: 700 }}>
                          ↓ {e.savings.toLocaleString(undefined, { maximumFractionDigits: 0 })} saved/mo
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
