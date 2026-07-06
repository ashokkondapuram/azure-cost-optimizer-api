import React, { useContext } from 'react';
import { Globe, TrendingDown, AlertTriangle, Zap } from 'lucide-react';
import { AppCtx } from '../App';
import PageHeader from '../components/PageHeader';

const MOCK_SUBS = [
  { id: 'sub-001', name: 'Production', spend: 18420, waste: 3200, findings: 47, savings: 3200, health: 72 },
  { id: 'sub-002', name: 'Development', spend: 5100,  waste: 1800, findings: 23, savings: 1800, health: 58 },
  { id: 'sub-003', name: 'Staging',     spend: 2800,  waste: 420,  findings: 9,  savings: 420,  health: 85 },
  { id: 'sub-004', name: 'Analytics',  spend: 7600,  waste: 900,  findings: 18, savings: 900,  health: 78 },
];

function HealthBar({ score }) {
  const cls = score >= 80 ? 'success' : score >= 60 ? 'warning' : 'critical';
  return (
    <div className="util-bar">
      <div className="util-bar__track">
        <div className={`util-bar__fill util-bar__fill--${cls === 'critical' ? 'critical' : cls === 'warning' ? 'warning' : ''}`}
          style={{ width: `${score}%` }} />
      </div>
      <span className={`util-bar__label util-bar__label--${cls === 'critical' ? 'critical' : cls === 'warning' ? 'warning' : ''}`}>{score}</span>
    </div>
  );
}

export default function CrossSubscription() {
  const { billingCurrency } = useContext(AppCtx);
  const currency = billingCurrency || 'CAD';

  const totalSpend   = MOCK_SUBS.reduce((s, r) => s + r.spend, 0);
  const totalWaste   = MOCK_SUBS.reduce((s, r) => s + r.waste, 0);
  const totalFindings = MOCK_SUBS.reduce((s, r) => s + r.findings, 0);
  const topOffender  = [...MOCK_SUBS].sort((a, b) => b.waste - a.waste)[0];

  return (
    <div className="page-shell cross-sub-page">
      <PageHeader title="Cross-Subscription Insights" subtitle="Aggregated cost and optimization data across all subscriptions" />

      <div className="grid-4" style={{ marginBottom: '1.25rem' }}>
        <div className="stat-card accent">
          <div className="stat-label">Total Spend</div>
          <div className="stat-value">{currency} {totalSpend.toLocaleString()}</div>
          <div className="stat-sub">{MOCK_SUBS.length} subscriptions</div>
        </div>
        <div className="stat-card danger">
          <div className="stat-label">Total Waste</div>
          <div className="stat-value">{currency} {totalWaste.toLocaleString()}</div>
          <div className="stat-sub">{Math.round((totalWaste/totalSpend)*100)}% of total spend</div>
        </div>
        <div className="stat-card warning">
          <div className="stat-label">Total Findings</div>
          <div className="stat-value">{totalFindings}</div>
          <div className="stat-sub">Across all subs</div>
        </div>
        <div className="stat-card success">
          <div className="stat-label">Top Offender</div>
          <div className="stat-value" style={{ fontSize: '1.1rem' }}>{topOffender.name}</div>
          <div className="stat-sub">{currency} {topOffender.waste.toLocaleString()} waste</div>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Subscription</th>
              <th>MTD Spend</th>
              <th>Estimated Waste</th>
              <th>Findings</th>
              <th>Potential Savings</th>
              <th>Health Score</th>
            </tr>
          </thead>
          <tbody>
            {MOCK_SUBS.map(s => (
              <tr key={s.id}>
                <td>
                  <span className="icon-inline"><Globe size={13} className="text-primary" />{s.name}</span>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text3)', fontFamily: 'var(--mono)' }}>{s.id}</div>
                </td>
                <td>{currency} {s.spend.toLocaleString()}</td>
                <td className="text-danger">{currency} {s.waste.toLocaleString()}</td>
                <td>
                  <span className={`badge ${s.findings > 30 ? 'badge-critical' : s.findings > 15 ? 'badge-medium' : 'badge-low'}`}>
                    {s.findings}
                  </span>
                </td>
                <td className="text-success">{currency} {s.savings.toLocaleString()}</td>
                <td><HealthBar score={s.health} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="alert alert--warning" style={{ marginTop: '1.25rem' }}>
        <AlertTriangle size={16} className="alert__icon" />
        <div>This view aggregates data from all subscriptions your account has access to. Connect additional subscriptions in <strong>Settings → Subscriptions</strong>.</div>
      </div>
    </div>
  );
}
