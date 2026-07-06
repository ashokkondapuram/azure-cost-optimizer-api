import React, { useState, useContext } from 'react';
import { Activity, Filter, CheckCircle2, XCircle, Clock, AlertTriangle, Zap, User } from 'lucide-react';
import { AppCtx } from '../App';
import PageHeader from '../components/PageHeader';
import { SubscriptionRequired } from '../components/QueryStates';

const MOCK_EVENTS = [
  { id: 1, ts: '2026-07-05 14:22', actor: 'ashok@corp.com', type: 'action_executed', resource: 'vm-prod-api-01', detail: 'Resized B4ms → B2s', outcome: 'success', savings: 320 },
  { id: 2, ts: '2026-07-05 11:08', actor: 'system',          type: 'finding_created', resource: 'aks-dev-cluster',  detail: 'New CRITICAL finding: idle node pool', outcome: 'info' },
  { id: 3, ts: '2026-07-04 19:00', actor: 'scheduler',       type: 'auto_schedule',  resource: 'dev VMs (12)',      detail: 'Nightly dev shutdown executed', outcome: 'success', savings: 180 },
  { id: 4, ts: '2026-07-04 16:45', actor: 'ravi@corp.com',   type: 'action_rejected', resource: 'disk-data-03',     detail: 'Delete rejected by approver', outcome: 'warning' },
  { id: 5, ts: '2026-07-03 09:14', actor: 'system',          type: 'drift_detected', resource: 'vm-prod-api-01',   detail: 'SKU changed Standard_D4s → D8s', outcome: 'warning' },
  { id: 6, ts: '2026-07-02 13:30', actor: 'infra-bot',       type: 'tag_fixed',      resource: 'storage-backup-1', detail: 'Applied cost-center=CC-101 tag', outcome: 'success' },
  { id: 7, ts: '2026-07-01 08:00', actor: 'scheduler',       type: 'auto_schedule',  resource: 'dev VMs (12)',      detail: 'Nightly dev shutdown executed', outcome: 'success', savings: 180 },
  { id: 8, ts: '2026-06-30 17:00', actor: 'system',          type: 'budget_alert',   resource: 'AKS Budget',        detail: 'Budget hit 100% — CAD 2,150 / 2,000', outcome: 'danger' },
];

const TYPE_ICON = {
  action_executed: <CheckCircle2 size={14} className="text-success" />,
  action_rejected: <XCircle     size={14} className="text-danger"  />,
  finding_created: <AlertTriangle size={14} className="text-warning" />,
  drift_detected:  <Zap         size={14} className="text-warning" />,
  auto_schedule:   <Clock       size={14} className="text-primary" />,
  tag_fixed:       <CheckCircle2 size={14} className="text-success" />,
  budget_alert:    <AlertTriangle size={14} className="text-danger"  />,
};

const TYPE_LABELS = {
  action_executed: 'Action Executed',
  action_rejected: 'Action Rejected',
  finding_created: 'Finding Created',
  drift_detected:  'Drift Detected',
  auto_schedule:   'Auto Schedule',
  tag_fixed:       'Tag Fixed',
  budget_alert:    'Budget Alert',
};

export default function OptimizationTimeline() {
  const { subscription } = useContext(AppCtx);
  const [typeFilter, setTypeFilter] = useState('all');

  const types = ['all', ...new Set(MOCK_EVENTS.map(e => e.type))];
  const events = typeFilter === 'all' ? MOCK_EVENTS : MOCK_EVENTS.filter(e => e.type === typeFilter);

  return (
    <div className="page-shell opt-timeline-page">
      <PageHeader title="Optimization Timeline" subtitle="Unified audit trail of all findings, actions, drifts and automated events" />
      {!subscription && <SubscriptionRequired />}
      {subscription && (
        <>
          <div className="toolbar" style={{ marginBottom: '1rem', flexWrap: 'wrap' }}>
            <Filter size={13} className="text-muted" />
            {types.map(t => (
              <button key={t} className={`chip${typeFilter===t?' active':''}`} onClick={() => setTypeFilter(t)}>
                {t === 'all' ? 'All events' : TYPE_LABELS[t] || t}
              </button>
            ))}
          </div>

          <div className="timeline">
            {events.map((e, i) => (
              <div key={e.id} className={`timeline-item timeline-item--${e.outcome}`}>
                <div className="timeline-item__dot">{TYPE_ICON[e.type]}</div>
                {i < events.length - 1 && <div className="timeline-item__line" />}
                <div className="timeline-item__body">
                  <div className="timeline-item__head">
                    <span className="timeline-item__type">{TYPE_LABELS[e.type]}</span>
                    <span className="timeline-item__ts">{e.ts}</span>
                  </div>
                  <div className="timeline-item__resource"><code>{e.resource}</code></div>
                  <div className="timeline-item__detail">{e.detail}</div>
                  <div className="timeline-item__footer">
                    <span className="icon-inline" style={{ fontSize: '0.72rem', color: 'var(--text3)' }}>
                      <User size={11} /> {e.actor}
                    </span>
                    {e.savings != null && <span className="text-success" style={{ fontSize: '0.72rem', fontWeight: 700 }}>↓ CAD {e.savings} saved</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
