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
          <div className="page-sub">{findings.length} findings &middot; real Azure data &middot; no mocks</div>
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, marginBottom: '1.25rem', flexWrap: 'wrap' }}>
        <select value={sevFilter} onChange={e => setSevFilter(e.target.value)}>
          <option value="">All Severities</option>
          {['CRITICAL','HIGH','MEDIUM','LOW','INFO'].map(s => (
            <option key={s} value={s}>{s}</option>
          ))}
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
                    <td style={{ color: 'var(--text)', fontWeight: 500, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {f.rule_name}
                    </td>
                    <td style={{ maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      <span title={f.resource_id}>{f.resource_name || (f.resource_id || '').split('/').pop()}</span>
                      {f.resource_group && (
                        <div style={{ fontSize: '0.72rem', color: 'var(--text3)' }}>{f.resource_group}</div>
                      )}
                    </td>
                    <td><span className="badge badge-info">{f.category}</span></td>
                    <td style={{ color: f.estimated_savings_usd > 0 ? 'var(--success)' : 'var(--text3)', fontWeight: 600 }}>
                      {f.estimated_savings_usd > 0
                        ? '$' + f.estimated_savings_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })
                        : '\u2014'}
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <div className="progress-bar-bg" style={{ width: 60 }}>
                          <div
                            className="progress-bar-fill"
                            style={{
                              width: (f.waste_score || 0) + '%',
                              background: f.waste_score > 75
                                ? 'var(--danger)'
                                : f.waste_score > 50
                                  ? 'var(--warning)'
                                  : 'var(--success)',
                            }}
                          />
                        </div>
                        <span style={{ fontSize: '0.78rem' }}>{f.waste_score}</span>
                      </div>
                    </td>
                    <td>
                      <span className={
                        'badge ' +
                        (f.status === 'resolved'
                          ? 'badge-low'
                          : f.status === 'acknowledged'
                          ? 'badge-medium'
                          : f.status === 'ignored'
                          ? 'badge-info'
                          : 'badge-high')
                      }>
                        {f.status}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: 'flex', gap: 6 }} onClick={e => e.stopPropagation()}>
                        {f.status === 'open' && (
                          <>
                            <button
                              className="btn btn-ghost"
                              style={{ padding: '4px 8px', fontSize: '0.72rem' }}
                              onClick={() => mut.mutate({ id: f.id, status: 'acknowledged' })}
                            >
                              Ack
                            </button>
                            <button
                              className="btn btn-ghost"
                              style={{ padding: '4px 8px', fontSize: '0.72rem' }}
                              onClick={() => mut.mutate({ id: f.id, status: 'resolved' })}
                            >
                              Resolve
                            </button>
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
              <button className="btn btn-ghost" style={{ padding: '4px 8px' }} onClick={() => setSelected(null)}>&#x2715;</button>
            </div>

            <div style={{ display: 'grid', gap: '0.75rem', fontSize: '0.86rem' }}>
              <div>
                <strong>Resource</strong>
                <br />
                <span style={{ color: 'var(--text2)', wordBreak: 'break-all' }}>{selected.resource_id}</span>
              </div>

              <div>
                <strong>Detail</strong>
                <br />
                <span style={{ color: 'var(--text2)' }}>{selected.detail}</span>
              </div>

              <div style={{ background: 'rgba(37,99,235,0.08)', border: '1px solid rgba(37,99,235,0.2)', borderRadius: 8, padding: '0.75rem' }}>
                <strong style={{ color: 'var(--primary)' }}>Recommendation</strong>
                <br />
                <span style={{ color: 'var(--text2)' }}>{selected.recommendation}</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.5rem' }}>
                <div style={{ background: 'var(--bg3)', borderRadius: 8, padding: '0.6rem 0.75rem' }}>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text3)', marginBottom: 2 }}>Est. Monthly Savings</div>
                  <div style={{ fontWeight: 700, color: selected.estimated_savings_usd > 0 ? 'var(--success)' : 'var(--text3)' }}>
                    {selected.estimated_savings_usd > 0
                      ? '$' + selected.estimated_savings_usd.toLocaleString(undefined, { maximumFractionDigits: 2 })
                      : 'N/A'}
                  </div>
                </div>
                <div style={{ background: 'var(--bg3)', borderRadius: 8, padding: '0.6rem 0.75rem' }}>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text3)', marginBottom: 2 }}>Waste Score</div>
                  <div style={{ fontWeight: 700, color: selected.waste_score > 75 ? 'var(--danger)' : selected.waste_score > 50 ? 'var(--warning)' : 'var(--success)' }}>
                    {selected.waste_score} / 100
                  </div>
                </div>
                <div style={{ background: 'var(--bg3)', borderRadius: 8, padding: '0.6rem 0.75rem' }}>
                  <div style={{ fontSize: '0.7rem', color: 'var(--text3)', marginBottom: 2 }}>Status</div>
                  <div style={{ fontWeight: 700 }}>{selected.status}</div>
                </div>
              </div>

              {selected.resource_group && (
                <div>
                  <strong>Resource Group</strong>
                  <br />
                  <span style={{ color: 'var(--text2)' }}>{selected.resource_group}</span>
                </div>
              )}

              {selected.location && (
                <div>
                  <strong>Location</strong>
                  <br />
                  <span style={{ color: 'var(--text2)' }}>{selected.location}</span>
                </div>
              )}

              {selected.annualized_savings_usd > 0 && (
                <div style={{ background: 'rgba(34,197,94,0.07)', border: '1px solid rgba(34,197,94,0.18)', borderRadius: 8, padding: '0.75rem' }}>
                  <strong style={{ color: 'var(--success)' }}>Annualized Savings</strong>
                  <br />
                  <span style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--success)' }}>
                    {'$' + selected.annualized_savings_usd.toLocaleString(undefined, { maximumFractionDigits: 0 }) + ' / year'}
                  </span>
                </div>
              )}

              {selected.confidence_score != null && (
                <div>
                  <strong>Confidence</strong>
                  <br />
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                    <div className="progress-bar-bg" style={{ width: 120 }}>
                      <div className="progress-bar-fill" style={{ width: selected.confidence_score + '%', background: 'var(--primary)' }} />
                    </div>
                    <span style={{ fontSize: '0.82rem' }}>{selected.confidence_score}%</span>
                  </div>
                </div>
              )}

              {selected.action_priority && (
                <div>
                  <strong>Action Priority</strong>
                  {' '}
                  <span className="badge badge-medium">{selected.action_priority}</span>
                </div>
              )}

              {selected.impact && (
                <div>
                  <strong>Impact</strong>
                  <br />
                  <span style={{ color: 'var(--text2)' }}>{selected.impact}</span>
                </div>
              )}

              {selected.evidence && Object.keys(selected.evidence).length > 0 && (
                <div>
                  <strong>Evidence</strong>
                  <pre style={{
                    background: 'var(--bg3)',
                    borderRadius: 7,
                    padding: '0.65rem 0.9rem',
                    fontSize: '0.78rem',
                    color: 'var(--text2)',
                    overflowX: 'auto',
                    marginTop: 6,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-all',
                  }}>
                    {JSON.stringify(selected.evidence, null, 2)}
                  </pre>
                </div>
              )}

              <div style={{ display: 'flex', gap: 8, marginTop: '0.5rem' }}>
                {selected.status === 'open' && (
                  <>
                    <button
                      className="btn btn-ghost"
                      onClick={() => { mut.mutate({ id: selected.id, status: 'acknowledged' }); setSelected(null); }}
                    >
                      <Eye size={14} /> Acknowledge
                    </button>
                    <button
                      className="btn btn-primary"
                      onClick={() => { mut.mutate({ id: selected.id, status: 'resolved' }); setSelected(null); }}
                    >
                      <CheckCircle size={14} /> Mark Resolved
                    </button>
                    <button
                      className="btn btn-danger"
                      onClick={() => { mut.mutate({ id: selected.id, status: 'ignored' }); setSelected(null); }}
                    >
                      <XCircle size={14} /> Ignore
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
