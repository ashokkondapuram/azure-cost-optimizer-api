import React, { useState, useContext } from 'react';
import { TrendingDown, CheckCircle2, Clock, BarChart3 } from 'lucide-react';
import { AppCtx } from '../App';
import PageHeader from '../components/PageHeader';
import { SubscriptionRequired } from '../components/QueryStates';

const MOCK_DATA = [
  { id: 1, resource: 'vm-prod-01', action: 'Resize B4ms → B2s', date: '2026-06-15', potential: 320, realised: 298, status: 'confirmed' },
  { id: 2, resource: 'aks-dev-cluster', action: 'Scale node pool 5→3', date: '2026-06-18', potential: 580, realised: 540, status: 'confirmed' },
  { id: 3, resource: 'disk-unused-07', action: 'Delete orphaned disk', date: '2026-06-22', potential: 48, realised: 48, status: 'confirmed' },
  { id: 4, resource: 'vm-staging-02', action: 'Deallocate nights+weekends', date: '2026-07-01', potential: 210, realised: null, status: 'pending' },
  { id: 5, resource: 'pip-old-gateway', action: 'Delete unused public IP', date: '2026-07-03', potential: 14, realised: null, status: 'pending' },
];

export default function SavingsRealised() {
  const { subscription, billingCurrency } = useContext(AppCtx);
  const currency = billingCurrency || 'CAD';
  const [filter, setFilter] = useState('all');

  const rows = filter === 'all' ? MOCK_DATA : MOCK_DATA.filter(r => r.status === filter);
  const totalPotential  = MOCK_DATA.reduce((s, r) => s + r.potential, 0);
  const totalRealised   = MOCK_DATA.filter(r => r.realised).reduce((s, r) => s + r.realised, 0);
  const realisationRate = Math.round((totalRealised / totalPotential) * 100);

  return (
    <div className="page-shell savings-realised-page">
      <PageHeader title="Savings Realised" subtitle="Track actual vs. potential savings after actions are executed" />

      {!subscription && <SubscriptionRequired message="Select a subscription." />}

      {subscription && (
        <>
          <div className="grid-3" style={{ marginBottom: '1.25rem' }}>
            <div className="stat-card success">
              <div className="stat-label">Realised Savings</div>
              <div className="stat-value">{currency} {totalRealised.toLocaleString()}</div>
              <div className="stat-sub">Confirmed post-action</div>
            </div>
            <div className="stat-card accent">
              <div className="stat-label">Potential Savings</div>
              <div className="stat-value">{currency} {totalPotential.toLocaleString()}</div>
              <div className="stat-sub">Across all executed actions</div>
            </div>
            <div className="stat-card warning">
              <div className="stat-label">Realisation Rate</div>
              <div className="stat-value">{realisationRate}%</div>
              <div className="stat-sub">Actual vs. projected</div>
            </div>
          </div>

          {/* Realisation bar */}
          <div className="card" style={{ marginBottom: '1.25rem' }}>
            <div className="card-section-head"><BarChart3 size={15} /><h3>Cumulative Realisation</h3></div>
            <div className="realisation-bar-wrap">
              <div className="realisation-bar">
                <div className="realisation-bar__fill" style={{ width: `${realisationRate}%` }} />
              </div>
              <span className="realisation-bar__label">{realisationRate}% of {currency} {totalPotential.toLocaleString()} realised</span>
            </div>
          </div>

          <div className="toolbar">
            <span className="toolbar__label">Filter</span>
            {['all', 'confirmed', 'pending'].map(f => (
              <button key={f} type="button"
                className={`chip${filter === f ? ' active' : ''}`}
                onClick={() => setFilter(f)}>
                {f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Resource</th>
                  <th>Action Taken</th>
                  <th>Date</th>
                  <th>Potential</th>
                  <th>Realised</th>
                  <th>Δ</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => {
                  const delta = r.realised != null ? r.realised - r.potential : null;
                  return (
                    <tr key={r.id}>
                      <td><code>{r.resource}</code></td>
                      <td>{r.action}</td>
                      <td>{r.date}</td>
                      <td>{currency} {r.potential}</td>
                      <td>{r.realised != null ? `${currency} ${r.realised}` : <span className="text-muted">—</span>}</td>
                      <td>
                        {delta != null && (
                          <span className={delta >= 0 ? 'text-success' : 'text-danger'}>
                            {delta >= 0 ? '+' : ''}{delta}
                          </span>
                        )}
                      </td>
                      <td>
                        {r.status === 'confirmed'
                          ? <span className="status-pill status-pill--live">Confirmed</span>
                          : <span className="status-pill"><Clock size={10} /> Pending</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
