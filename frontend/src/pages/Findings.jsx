import React, { useContext, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { CheckCircle, XCircle, Eye, AlertTriangle } from 'lucide-react';
import { AppCtx } from '../App';
import { fetchFindings, updateFindingStatus } from '../api/azure';

const SEV_MAP = {
  CRITICAL: 'badge badge-critical',
  HIGH:     'badge badge-high',
  MEDIUM:   'badge badge-medium',
  LOW:      'badge badge-low',
  INFO:     'badge badge-info',
};

export default function Findings() {
  const { subscription } = useContext(AppCtx);
  const qc = useQueryClient();
  const [sevFilter, setSevFilter]  = useState('');
  const [catFilter, setCatFilter]  = useState('');
  const [statusFilter, setStatus]  = useState('open');
  const [selected, setSelected]    = useState(null);

  const { data: findings = [], isLoading } = useQuery({
    queryKey: ['findings', subscription, sevFilter, catFilter, statusFilter],
    queryFn:  () => fetchFindings({
      subscription_id: subscription || undefined,
      severity: sevFilter || undefined,
      category: catFilter || undefined,
      status:   statusFilter || undefined,
      limit: 500,
    }),
    enabled: true,
  });

  const mut = useMutation({
    mutationFn: ({ id, status }) => updateFindingStatus(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['findings'] }),
  });

  const categories = [...new Set(findings.map(f => f.category))];

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Findings</div>
          <div className="page-sub">{findings.length} findings · real Azure data · no mocks</div>
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, marginBottom: '1.25rem', flexWrap: 'wrap' }}>
        <select value={sevFilter} onChange={e => setSevFilter(e.target.value)}>
          <option value="">All Severities</option>
          {['CRITICAL','HIGH','MEDIUM','LOW','INFO'].map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={catFilter} onChange={e => setCatFilter(e.target.value)}>
          <option value="">All Categories</option>
          {categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={statusFilter} onChange={e => setStatus(e.target.value)}>
          <option value="open">Open</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="resolved">Resolved</option>
          <option value="ignored">Ignored</option>
          <option value="">All</option>
        </select>
      </div>

      <div className="card">
        {isLoading ? (
          <div className="empty-state"><div className="spin" /></div>
        ) : findings.length === 0 ? (
          <div className="empty-state">
            <AlertTriangle size={36} />
            <p>No findings. Run an analysis from the Dashboard or adjust filters.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Rule</th>
                  <th>Resource</th>
                  <th>Category</th>
                  <th>Est. Savings/mo</th>
                  <th>Score</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {findings.map(f => (
                  <tr key={f.id} className="finding-row" onClick={() => setSelected(f)}>
                    <td><span className={SEV_MAP[f.severity] || 'badge'}>{f.severity}</span></td>
                    <td style={{ color: 'var(--text)', fontWeight: 500, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.rule_name}</td>
                    <td style={{ maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      <span title={f.resource_id}>{f.resource_name || f.resource_id?.split('/').pop()}</span>
                      {f.resource_group && <div style={{ fontSize: '0.72rem', color: 'var(--text3)' }}>{f.resource_group}</div>}
                    </td>
                    <td><span className="badge badge-info">{f.category}</span></td>
                    <td style={{ color: f.estimated_savings_usd > 0 ? 'var(--success)' : 'var(--text3)', fontWeight: 600 }}>
                      {f.estimated_savings_usd > 0 ? `$${f.estimated_savings_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '—'}
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div className="progress-bar-bg" style={{ width: 60 }}>
                          <div className="progress-bar-fill" style={{ width: `${f.waste_score || 0}%`, background: f.waste_score > 75 ? 'var(--danger)' : f.waste_score > 50 ? 'var(--warning)' : 'var(--success)' }} />
                        </div>
                        <span style={{ fontSize: '0.78rem' }}>{f.waste_score}</span>
                      </div>
                    </td>
                    <td><span className={`badge ${f.status === 'resolved' ? 'badge-low' : f.status === 'acknowledged' ? 'badge-medium' : f.status === 'ignored' ? 'badge-info' : 'badge-high'}`}>{f.status}</span></td>
                    <td>
                      <div style={{ display: 'flex', gap: 6 }} onClick={e => e.stopPropagation()}>
                        {f.status === 'open' && (
                          <>
                            <button className="btn btn-ghost" style={{ padding: '4px 8px', fontSize: '0.72rem' }} onClick={() => mut.mutate({ id: f.id, status: 'acknowledged' })}>Ack</button>
                            <button className="btn btn-ghost" style={{ padding: '4px 8px', fontSize: '0.72rem' }} onClick={() => mut.mutate({ id: f.id, status: 'resolved' })}>Resolve</button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Detail modal */}
      {selected && (
        <div className="modal-overlay" onClick={() => setSelected(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.25rem' }}>
              <div>
                <div className="modal-title" style={{ marginBottom: 6 }}>{selected.rule_name}</div>
                <span className={SEV_MAP[selected.severity] || 'badge'}>{selected.severity}</span>
                {' '}
                <span className="badge badge-info">{selected.category}</span>
              </div>
              <button className="btn btn-ghost" style={{ padding: '4px 8px' }} onClick={() => setSelected(null)}>✕</button>
            </div>
            <div style={{ display: 'grid', gap: '0.75rem', fontSize: '0.86rem' }}>
              <div><strong>Resource</strong><br /><span style={{ color: 'var(--text2)', wordBreak: 'break-all' }}>{selected.resource_id}</span></div>
              <div><strong>Detail</strong><br /><span style={{ color: 'var(--text2)' }}>{selected.detail}</span></div>
              <div style={{ background: 'rgba(37,99,235,0.0