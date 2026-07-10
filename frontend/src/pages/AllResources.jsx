import React, { useContext, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AppCtx } from '../App';
import { fetchStorage, fetchPublicIPs, fetchSQL, fetchKeyVaults, fetchResourceGroups } from '../api/azure';

const TABS = [
  { id: 'storage',   label: 'Storage' },
  { id: 'publicips', label: 'Public IPs' },
  { id: 'sql',       label: 'SQL DBs' },
  { id: 'kv',        label: 'Key Vaults' },
  { id: 'rgs',       label: 'Resource Groups' },
];

export default function AllResources() {
  const { subscription } = useContext(AppCtx);
  const [tab, setTab]   = useState('storage');
  const [q,   setQ]     = useState('');

  const p = { subscription_id: subscription };
  const { data: storage = [], isLoading: l1 }  = useQuery({ queryKey: ['storage', subscription],  queryFn: () => fetchStorage(p),        enabled: !!subscription });
  const { data: ips = [],     isLoading: l2 }  = useQuery({ queryKey: ['ips', subscription],      queryFn: () => fetchPublicIPs(p),      enabled: !!subscription });
  const { data: sql = [],     isLoading: l3 }  = useQuery({ queryKey: ['sql', subscription],      queryFn: () => fetchSQL(p),            enabled: !!subscription });
  const { data: kvs = [],     isLoading: l4 }  = useQuery({ queryKey: ['kv', subscription],       queryFn: () => fetchKeyVaults(p),      enabled: !!subscription });
  const { data: rgs = [],     isLoading: l5 }  = useQuery({ queryKey: ['rgs', subscription],      queryFn: () => fetchResourceGroups(p), enabled: !!subscription });

  const dataMap  = { storage, publicips: ips, sql, kv: kvs, rgs };
  const loadMap  = { storage: l1, publicips: l2, sql: l3, kv: l4, rgs: l5 };
  const rows     = (dataMap[tab] || []).filter(r => !q || (r.name || '').toLowerCase().includes(q.toLowerCase()));
  const loading  = loadMap[tab];

  function renderTable() {
    if (loading) return <div className="empty-state"><div className="spin" /></div>;
    if (rows.length === 0) return <div className="empty-state"><p>No {tab} resources found.</p></div>;
    if (tab === 'storage') return (
      <table><thead><tr><th>Name</th><th>Location</th><th>SKU</th><th>Access Tier</th><th>Kind</th><th>TLS Min</th></tr></thead>
        <tbody>{rows.map((r, i) => { const p = r.properties || {}; return (
          <tr key={i}><td style={{ color: 'var(--text)', fontWeight: 500 }}>{r.name}</td><td>{r.location}</td>
            <td style={{ fontSize: '0.8rem', fontFamily: 'monospace' }}>{r.sku?.name}</td>
            <td>{p.accessTier || '—'}</td><td>{r.kind}</td>
            <td>{p.minimumTlsVersion || '—'}</td></tr>
        )})}</tbody></table>
    );
    if (tab === 'publicips') return (
      <table><thead><tr><th>Name</th><th>Location</th><th>Allocation</th><th>IP Address</th><th>SKU</th><th>Associated To</th></tr></thead>
        <tbody>{rows.map((r, i) => { const p = r.properties || {}; return (
          <tr key={i}><td style={{ color: p.ipConfiguration ? 'var(--text)' : 'var(--danger)', fontWeight: 500 }}>{r.name}</td>
            <td>{r.location}</td><td>{p.publicIPAllocationMethod}</td>
            <td style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{p.ipAddress || '—'}</td>
            <td>{r.sku?.name}</td>
            <td>{p.ipConfiguration ? <span className="badge badge-low">Attached</span> : <span className="badge badge-critical">Idle</span>}</td></tr>
        )})}</tbody></table>
    );
    if (tab === 'sql') return (
      <table><thead><tr><th>Name</th><th>Location</th><th>SKU Tier</th><th>DTUs</th><th>Status</th></tr></thead>
        <tbody>{rows.map((r, i) => { const p = r.properties || {}; return (
          <tr key={i}><td style={{ color: 'var(--text)', fontWeight: 500 }}>{r.name}</td><td>{r.location}</td>
            <td>{r.sku?.tier || '—'}</td><td>{r.sku?.capacity || '—'}</td>
            <td><span className={`badge ${p.status === 'Online' ? 'badge-low' : 'badge-medium'}`}>{p.status}</span></td></tr>
        )})}</tbody></table>
    );
    if (tab === 'kv') return (
      <table><thead><tr><th>Name</th><th>Location</th><th>SKU</th><th>Soft Delete</th><th>Purge Protection</th></tr></thead>
        <tbody>{rows.map((r, i) => { const p = r.properties || {}; return (
          <tr key={i}><td style={{ color: 'var(--text)', fontWeight: 500 }}>{r.name}</td><td>{r.location}</td>
            <td>{p.sku?.name}</td>
            <td>{p.enableSoftDelete ? <span className="badge badge-low">On</span> : <span className="badge badge-critical">Off</span>}</td>
            <td>{p.enablePurgeProtection ? <span className="badge badge-low">On</span> : <span className="badge badge-medium">Off</span>}</td></tr>
        )})}</tbody></table>
    );
    if (tab === 'rgs') return (
      <table><thead><tr><th>Name</th><th>Location</th><th>Provisioning</th><th>Tags</th></tr></thead>
        <tbody>{rows.map((r, i) => (
          <tr key={i}><td style={{ color: 'var(--text)', fontWeight: 500 }}>{r.name}</td><td>{r.location}</td>
            <td><span className="badge badge-low">{r.properties?.provisioningState}</span></td>
            <td>{Object.entries(r.tags || {}).slice(0, 3).map(([k, v]) => <span key={k} className="tag">{k}: {v}</span>)}</td></tr>
        ))}</tbody></table>
    );
  }

  return (
    <div>
      <div className="page-header">
        <div><div className="page-title">All Resources</div><div className="page-sub">Live Azure Resource Manager data</div></div>
        <input placeholder="Filter by name…" value={q} onChange={e => setQ(e.target.value)} style={{ width: 220 }} />
      </div>
      <div style={{ display: 'flex', gap: 8, marginBottom: '1.25rem', flexWrap: 'wrap' }}>
        {TABS.map(t => <button key={t.id} className={`btn ${tab === t.id ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTab(t.id)}>{t.label} ({(dataMap[t.id] || []).length})</button>)}
      </div>
      <div className="card"><div className="table-wrap">{renderTable()}</div></div>
    </div>
  );
}
