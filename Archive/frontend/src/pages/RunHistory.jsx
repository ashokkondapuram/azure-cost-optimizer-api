import React, { useContext, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity } from 'lucide-react';
import { AppCtx } from '../App';
import { fetchRuns, fetchRun } from '../api/azure';

const SEV_MAP = { CRITICAL: 'badge-critical', HIGH: 'badge-high', MEDIUM: 'badge-medium', LOW: 'badge-low', INFO: 'badge-info' };

export default function RunHistory() {
  const { subscription } = useContext(AppCtx);
  const [selected, setSelected] = useState(null);
  const [detailId, setDetailId] = useState(null);

  const { data: runs = [], isLoading } = useQuery({
    queryKey: ['runs', subscription],
    queryFn: () => fetchRuns({ subscription_id: subscription, limit: 50 }),
    enabled: !!subscription,
  });

  const { data: detail } = useQuery({
    queryKey: ['run-detail', detailId],
    queryFn: () => fetchRun(detailId),
    enabled: !!detailId,
  });

  const handleOpen = (run) => { setSelected(run); setDetailId(run.id); };

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Run History</div>
          <div className="page-sub">{runs.length} analysis runs · click a row to inspect all findings</div>
        </div>
      </div>

      <div className="card">
        {isLoading ? <div className="empty-state"><div className="spin" /></div> :
         runs.length === 0 ? <div className="empty-state"><Activity size={28} /><p>No runs yet. Use the Dashboard to trigger an analysis.</p></div> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Subscription</th><th>Profile</th><th>Findings</th><th>Critical</th><th>High</th><th>Est. Savings/mo</th></tr></thead>
              <tbody>
                {runs.map((r, i) => (
                  <tr key={i} style={{ cursor: 'pointer' }} onClick={() => handleOpen(r)}>
                    <td style={{ color: 'var(--text)', fontWeight: 500, whiteSpace: 'nowrap' }}>
                      {new Date(r.analyzed_at).toLocaleString()}
                    </td>
                    <td style={{ fontSize: '0.78rem', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.subscription_id}</td>
                    <td><span className="badge badge-info">{r.profile || 'default'}</span></td>
                    <td style={{ fontWeight: 600 }}>{r.total_findings}</td>
                    <td><span style={{ color: 'var(--danger)', fontWeight: 700 }}>{r.critical_count || 0}</span></td>
                    <td><span style={{ color: '#fca5a5', fontWeight: 700 }}>{r.high_count || 0}</span></td>
                    <td style={{ color: 'var(--success)', fontWeight: 700 }}>${(r.total_savings_usd || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selected && (
        <div className="modal-overlay" onClick={() => setSelected(null)}>
          <div className="modal" style={{ maxWidth: '90vw', width: 900 }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <div className="modal-title">Run: {new Date(selected.analyzed_at).toLocaleString()}</div>
              <button className="btn btn-ghost" onClick={() => setSelected(null)}>✕</button>
            </div>
            {!detail ? <div className="empty-state"><div className="spin" /></div> : (
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Severity</th><th>Rule</th><th>Resource</th><th>Savings</th><th>Score</th><th>Status</th></tr></thead>
                  <tbody>
                    {(detail.findings || []).map((f, i) => (
                      <tr key={i}>
                        <td><span className={`badge ${SEV_MAP[f.severity] || ''}`}>{f.severity}</span></td>
                        <td style={{ color: 'var(--text)', fontWeight: 500, fontSize: '0.83rem' }}>{f.rule_name}</td>
                        <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.8rem' }}>{f.resource_name || f.resource_id?.split('/').pop()}</td>
                        <td style={{ color: f.estimated_savings_usd > 0 ? 'var(--success)' : 'var(--text3)', fontWeight: 600 }}>
                          {f.estimated_savings_usd > 0 ? `$${f.estimated_savings_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '—'}
                        </td>
                        <td>{f.waste_score}</td>
                        <td><span className="badge badge-info">{f.status}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
