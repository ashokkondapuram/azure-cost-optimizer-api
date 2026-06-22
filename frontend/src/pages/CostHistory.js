import React, { useState } from 'react';
import { mockHistory } from '../api/mockData';

export default function CostHistory() {
  const [filter, setFilter] = useState('');

  const filtered = mockHistory.filter(r =>
    !filter ||
    r.resource_group?.toLowerCase().includes(filter.toLowerCase()) ||
    r.timeframe?.toLowerCase().includes(filter.toLowerCase())
  );

  const TIMEFRAME_COLOR = {
    'MonthToDate':        'badge-blue',
    'BillingMonthToDate': 'badge-orange',
    'TheLastMonth':       'badge-gray',
    'WeekToDate':         'badge-green',
  };

  return (
    <div>
      <div className="page-header">
        <h1>Cost Query History</h1>
        <p>All Azure cost queries stored in PostgreSQL</p>
      </div>

      <div className="stat-row">
        <div className="stat-card">
          <span className="stat-icon">📋</span>
          <div className="stat-label">Total Queries</div>
          <div className="stat-value blue">{mockHistory.length}</div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">📅</span>
          <div className="stat-label">Last Queried</div>
          <div className="stat-value" style={{ fontSize:'0.95rem' }}>2026-06-22</div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">🗂</span>
          <div className="stat-label">Unique RGs</div>
          <div className="stat-value green">{[...new Set(mockHistory.map(r => r.resource_group).filter(Boolean))].length}</div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h2>Query Log</h2>
          <span className="badge badge-blue">{filtered.length} records</span>
        </div>
        <div className="card-body">
          <div className="controls">
            <input type="text" placeholder="🔍  Filter by resource group or timeframe…"
              value={filter} onChange={e => setFilter(e.target.value)} style={{ width:320 }} />
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Query ID</th>
                  <th>Subscription</th>
                  <th>Resource Group</th>
                  <th>Timeframe</th>
                  <th>Queried At</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r,i) => (
                  <tr key={i}>
                    <td style={{ fontFamily:'monospace', fontSize:'0.78rem', color:'#9ba3b8' }}>{r.id.slice(0,12)}…</td>
                    <td style={{ fontFamily:'monospace', fontSize:'0.78rem' }}>{r.subscription_id.slice(0,12)}…</td>
                    <td><strong>{r.resource_group || '—'}</strong></td>
                    <td><span className={`badge ${TIMEFRAME_COLOR[r.timeframe]||'badge-gray'}`}>{r.timeframe}</span></td>
                    <td style={{ color:'#9ba3b8', fontSize:'0.78rem' }}>{r.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
