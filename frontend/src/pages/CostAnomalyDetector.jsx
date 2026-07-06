import React, { useState, useContext } from 'react';
import { Zap, TrendingUp, AlertTriangle, CheckCircle, Info } from 'lucide-react';
import { AppCtx } from '../App';
import PageHeader from '../components/PageHeader';
import { SubscriptionRequired } from '../components/QueryStates';

const MOCK_ANOMALIES = [
  { id: 1, date: '2026-07-03', service: 'Compute', spike: 340, baseline: 180, pct: 89, severity: 'high',   status: 'open',     reason: 'VM SKU upgraded unexpectedly' },
  { id: 2, date: '2026-07-01', service: 'AKS',     spike: 620, baseline: 420, pct: 48, severity: 'medium', status: 'open',     reason: 'Node pool auto-scaled to 8 nodes' },
  { id: 3, date: '2026-06-28', service: 'Storage',  spike: 95,  baseline: 42,  pct: 126, severity: 'high',  status: 'resolved', reason: 'Backup retention policy change' },
  { id: 4, date: '2026-06-25', service: 'Network',  spike: 280, baseline: 260, pct: 8,  severity: 'low',   status: 'resolved', reason: 'Within normal range' },
];

const SPARKLINE = [180, 185, 178, 190, 183, 179, 340]; // last 7 days mock

function Sparkline({ data, anomalyIdx }) {
  const max = Math.max(...data, 1);
  const w = 80, h = 32;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - (v / max) * h}`).join(' ');
  return (
    <svg width={w} height={h} className="anomaly-sparkline">
      <polyline points={pts} fill="none" stroke="var(--primary)" strokeWidth="1.5" />
      {data.map((v, i) => i === anomalyIdx && (
        <circle key={i} cx={(i / (data.length - 1)) * w} cy={h - (v / max) * h} r="3" fill="var(--danger)" />
      ))}
    </svg>
  );
}

export default function CostAnomalyDetector() {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const currency = billingCurrency || 'CAD';
  const [statusFilter, setStatusFilter] = useState('all');

  const rows = statusFilter === 'all' ? MOCK_ANOMALIES : MOCK_ANOMALIES.filter(a => a.status === statusFilter);
  const openCount = MOCK_ANOMALIES.filter(a => a.status === 'open').length;
  const highCount = MOCK_ANOMALIES.filter(a => a.severity === 'high').length;

  return (
    <div className="page-shell anomaly-page">
      <PageHeader title="Cost Anomaly Detector" subtitle="Automatic spike detection compared to your 30-day baseline" />
      {!subscription && <SubscriptionRequired />}
      {subscription && (
        <>
          <div className="grid-3" style={{ marginBottom: '1.25rem' }}>
            <div className="stat-card danger"><div className="stat-label">Open Anomalies</div><div className="stat-value">{openCount}</div></div>
            <div className="stat-card warning"><div className="stat-label">High Severity</div><div className="stat-value">{highCount}</div></div>
            <div className="stat-card success"><div className="stat-label">Resolved</div><div className="stat-value">{MOCK_ANOMALIES.filter(a=>a.status==='resolved').length}</div></div>
          </div>

          <div className="toolbar">
            {['all','open','resolved'].map(f => (
              <button key={f} className={`chip${statusFilter===f?' active':''}`} onClick={() => setStatusFilter(f)}>
                {f.charAt(0).toUpperCase()+f.slice(1)}
              </button>
            ))}
          </div>

          <div className="table-wrap" style={{ marginTop: '0.75rem' }}>
            <table>
              <thead>
                <tr><th>Date</th><th>Service</th><th>Trend</th><th>Spike</th><th>Baseline</th><th>% Change</th><th>Reason</th><th>Severity</th><th>Status</th></tr>
              </thead>
              <tbody>
                {rows.map(a => (
                  <tr key={a.id}>
                    <td style={{ fontFamily: 'var(--mono)', fontSize: '0.78rem' }}>{a.date}</td>
                    <td>{a.service}</td>
                    <td><Sparkline data={SPARKLINE} anomalyIdx={6} /></td>
                    <td className="text-danger" style={{ fontWeight: 700 }}>{currency} {a.spike}</td>
                    <td style={{ color: 'var(--text3)' }}>{currency} {a.baseline}</td>
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

          <div className="alert alert--info" style={{ marginTop: '1rem' }}>
            <Info size={14} className="alert__icon" />
            Anomalies are detected when daily spend exceeds the 30-day rolling average by more than 15%. Connect Azure Cost Management API for live data.
          </div>
        </>
      )}
    </div>
  );
}
