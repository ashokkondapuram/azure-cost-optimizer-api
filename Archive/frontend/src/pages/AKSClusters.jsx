import React, { useContext, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Boxes, AlertTriangle } from 'lucide-react';
import { AppCtx } from '../App';
import { fetchAKS } from '../api/azure';

const STATE_COLOR = { Running: 'var(--success)', Stopped: 'var(--warning)', Failed: 'var(--danger)', Creating: 'var(--accent)' };

export default function AKSClusters() {
  const { subscription } = useContext(AppCtx);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState(null);

  const { data: clusters = [], isLoading } = useQuery({
    queryKey: ['aks', subscription],
    queryFn: () => fetchAKS({ subscription_id: subscription }),
    enabled: !!subscription,
  });

  const filtered = clusters.filter(c =>
    !search ||
    (c.name || '').toLowerCase().includes(search.toLowerCase()) ||
    (c.location || '').toLowerCase().includes(search.toLowerCase())
  );

  const running  = clusters.filter(c => c.properties?.powerState?.code === 'Running').length;
  const stopped  = clusters.filter(c => c.properties?.powerState?.code === 'Stopped').length;
  const totalNodes = clusters.reduce((s, c) => {
    const pools = c.properties?.agentPoolProfiles || [];
    return s + pools.reduce((ps, p) => ps + (p.count || 0), 0);
  }, 0);
  const versions = [...new Set(clusters.map(c => c.properties?.kubernetesVersion).filter(Boolean))];

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">AKS Clusters</div>
          <div className="page-sub">Live from Azure Resource Manager · {clusters.length} clusters</div>
        </div>
        <input placeholder="Search name, location…" value={search} onChange={e => setSearch(e.target.value)} style={{ width: 240 }} />
      </div>

      <div className="grid-4" style={{ marginBottom: '1.5rem' }}>
        <div className="stat-card accent"><div className="stat-label">Total Clusters</div><div className="stat-value">{clusters.length}</div><div className="stat-sub">{running} running</div></div>
        <div className="stat-card warning"><div className="stat-label">Stopped</div><div className="stat-value">{stopped}</div><div className="stat-sub">Not incurring compute</div></div>
        <div className="stat-card success"><div className="stat-label">Total Nodes</div><div className="stat-value">{totalNodes.toLocaleString()}</div><div className="stat-sub">Across all pools</div></div>
        <div className="stat-card purple"><div className="stat-label">K8s Versions</div><div className="stat-value">{versions.length}</div><div className="stat-sub">{versions[0] || '—'} (latest in use)</div></div>
      </div>

      <div className="card">
        {isLoading ? <div className="empty-state"><div className="spin" /></div> :
         filtered.length === 0 ? <div className="empty-state"><AlertTriangle size={28} /><p>No AKS clusters found in this subscription.</p></div> : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th><th>Version</th><th>Location</th>
                  <th>Node Pools</th><th>Nodes</th><th>State</th>
                  <th>SKU</th><th>Network</th><th>Tags</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c, i) => {
                  const p = c.properties || {};
                  const pools = p.agentPoolProfiles || [];
                  const nodeCount = pools.reduce((s, pp) => s + (pp.count || 0), 0);
                  const state = p.powerState?.code || p.provisioningState || 'Unknown';
                  const tags = c.tags || {};
                  return (
                    <tr key={i} style={{ cursor: 'pointer' }} onClick={() => setSelected(c)}>
                      <td style={{ color: 'var(--text)', fontWeight: 600 }}>{c.name}</td>
                      <td style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{p.kubernetesVersion || '—'}</td>
                      <td>{c.location}</td>
                      <td>{pools.length}</td>
                      <td>{nodeCount}</td>
                      <td><span style={{ color: STATE_COLOR[state] || 'var(--text2)', fontWeight: 600, fontSize: '0.8rem' }}>● {state}</span></td>
                      <td style={{ fontSize: '0.78rem' }}>{c.sku?.name || '—'}</td>
                      <td style={{ fontSize: '0.78rem' }}>{p.networkProfile?.networkPlugin || '—'}</td>
                      <td>{Object.entries(tags).slice(0, 2).map(([k, v]) => <span key={k} className="tag">{k}: {v}</span>)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selected && (
        <div className="modal-overlay" onClick={() => setSelected(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
              <div className="modal-title">{selected.name}</div>
              <button className="btn btn-ghost" onClick={() => setSelected(null)}>✕</button>
            </div>
            <div style={{ fontSize: '0.85rem', display: 'grid', gap: '0.75rem' }}>
              <div><strong>Resource ID</strong><br /><span style={{ color: 'var(--text2)', wordBreak: 'break-all', fontSize: '0.78rem' }}>{selected.id}</span></div>
              <div><strong>Location</strong> · {selected.location}</div>
              <div><strong>K8s Version</strong> · {selected.properties?.kubernetesVersion}</div>
              <div><strong>Node Pools</strong></div>
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Pool Name</th><th>Mode</th><th>Count</th><th>VM Size</th><th>OS</th></tr></thead>
                  <tbody>
                    {(selected.properties?.agentPoolProfiles || []).map((pp, i) => (
                      <tr key={i}>
                        <td style={{ fontWeight: 500 }}>{pp.name}</td>
                        <td><span className={`badge ${pp.mode === 'System' ? 'badge-critical' : 'badge-info'}`}>{pp.mode}</span></td>
                        <td>{pp.count}</td>
                        <td style={{ fontFamily: 'monospace', fontSize: '0.78rem' }}>{pp.vmSize}</td>
                        <td>{pp.osType}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <strong>Tags</strong><br />
                {Object.entries(selected.tags || {}).map(([k, v]) => <span key={k} className="tag">{k}: {v}</span>)}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
