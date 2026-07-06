import React, { useState, useContext } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle, Info, RefreshCw } from 'lucide-react';
import { AppCtx } from '../App';
import PageHeader from '../components/PageHeader';
import { SubscriptionRequired, LoadingState, ErrorState } from '../components/QueryStates';
import { fetchCostChanges } from '../api/azure';

function Sparkline({ data }) {
  if (!data || data.length < 2) return null;
  const max = Math.max(...data, 1);
  const w = 80, h = 32;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - (v / max) * h}`).join(' ');
  return (
    <svg width={w} height={h} className="anomaly-sparkline">
      <polyline points={pts} fill="none" stroke="var(--primary)" strokeWidth="1.5" />
      <circle
        cx={(( data.length - 1) / (data.length - 1)) * w}
        cy={h - (data[data.length - 1] / max) * h}
        r="3"
        fill="var(--danger)"
      />
    </svg>
  );
}

/** Classify a cost change record as an anomaly */
function toAnomalyRow(change, currency) {
  const spike    = Number(change.current_cost   || change.cost       || 0);
  const baseline = Number(change.previous_cost  || change.base_cost  || 0);
  const pct      = baseline > 0 ? Math.round(((spike - baseline) / baseline) * 100) : 0;
  const severity = pct >= 50 ? 'high' : pct >= 20 ? 'medium' : 'low';
  return {
    id:       change.id || change.resource_id || `${change.service}-${change.date}`,
    date:     change.date || change.period || '—',
    service:  change.service || change.service_name || change.resource_type || 'Unknown',
    spike,
    baseline,
    pct,
    severity,
    status:   change.status || 'open',
    reason:   change.reason || change.description || 'Cost increase detected',
  };
}

export default function CostAnomalyDetector() {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const currency     = billingCurrency || 'CAD';
  const [statusFilter, setStatusFilter] = useState('all');

  const { data: rawChanges, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['cost-changes', subscription],
    queryFn:  () => fetchCostChanges({ subscription_id: subscription, threshold_pct: 15 }),
    enabled:  !!subscription,
    staleTime: 5 * 60_000,
    select: data => {
      const list = Array.isArray(data) ? data
        : Array.isArray(data?.items)   ? data.items
        : Array.isArray(data?.changes) ? data.changes
        : [];
      // Only show rows that are actually spikes (pct > 0)
      return list
        .map(c => toAnomalyRow(c, currency))
        .filter(a => a.pct > 0)
        .sort((a, b) => b.pct - a.pct);
    },
  });

  const anomalies  = rawChanges || [];
  const rows       = statusFilter === 'all' ? anomalies : anomalies.filter(a => a.status === statusFilter);
  const openCount  = anomalies.filter(a => a.status === 'open').length;
  const highCount  = anomalies.filter(a => a.severity === 'high').length;
  const resolvedCount = anomalies.filter(a => a.status === 'resolved').length;

  return (
    <div className="page-shell anomaly-page">
      <PageHeader title="Cost Anomaly Detector" subtitle="Spend spikes vs. your 30-day rolling baseline">
        <button className="btn btn-sm btn-ghost" onClick={refetch} title="Refresh"><RefreshCw size={13} /> Refresh</button>
      </PageHeader>

      {!subscription && <SubscriptionRequired />}
      {subscription && isLoading && <LoadingState message="Analysing cost changes…" />}
      {subscription && isError   && <ErrorState message={error?.message || 'Failed to load cost changes.'} />}
      {subscription && !isLoading && !isError && (
        <>
          <div className="grid-3" style={{ marginBottom: '1.25rem' }}>
            <div className="stat-card danger"><div className="stat-label">Open Anomalies</div><div className="stat-value">{openCount}</div></div>
            <div className="stat-card warning"><div className="stat-label">High Severity</div><div className="stat-value">{highCount}</div></div>
            <div className="stat-card success"><div className="stat-label">Resolved</div><div className="stat-value">{resolvedCount}</div></div>
          </div>

          <div className="toolbar">
            {['all', 'open', 'resolved'].map(f => (
              <button key={f} className={`chip${statusFilter===f?' active':''}`} onClick={() => setStatusFilter(f)}>
                {f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>

          {rows.length === 0 ? (
            <div className="empty-state" style={{ padding: '2rem' }}>
              <AlertTriangle size={28} />
              <p>
                {anomalies.length === 0
                  ? 'No cost changes found. Make sure costs are synced for this subscription.'
                  : 'No anomalies match the selected filter.'}
              </p>
            </div>
          ) : (
            <div className="table-wrap" style={{ marginTop: '0.75rem' }}>
              <table>
                <thead>
                  <tr><th>Date</th><th>Service</th><th>Spike</th><th>Baseline</th><th>% Change</th><th>Reason</th><th>Severity</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {rows.map(a => (
                    <tr key={a.id}>
                      <td style={{ fontFamily: 'var(--mono)', fontSize: '0.78rem' }}>{a.date}</td>
                      <td>{a.service}</td>
                      <td className="text-danger" style={{ fontWeight: 700 }}>{currency} {a.spike.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                      <td style={{ color: 'var(--text3)' }}>{currency} {a.baseline.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                      <td>
                        <span className={`anomaly-pct anomaly-pct--${a.severity}`}>+{a.pct}%</span>
                      </td>
                      <td style={{ maxWidth: 200, fontSize: '0.78rem', color: 'var(--text2)' }}>{a.reason}</td>
                      <td><span className={`badge badge-${a.severity === 'high' ? 'critical' : a.severity === 'medium' ? 'medium' : 'low'}`}>{a.severity}</span></td>
                      <td>
                        {a.status === 'open'
                          ? <span className="badge badge-medium"><AlertTriangle size={10} /> Open</span>
                          : <span className="badge badge-ok"><CheckCircle size={10} /> Resolved</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="alert alert--info" style={{ marginTop: '1rem' }}>
            <Info size={14} className="alert__icon" />
            Anomalies detected when daily spend exceeds the rolling average by more than 15%.
          </div>
        </>
      )}
    </div>
  );
}
