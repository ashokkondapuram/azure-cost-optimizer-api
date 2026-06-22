import React, { useState, useMemo } from 'react';
import { mockResources, mockSubscriptions } from '../api/mockData';
import StatusDot from '../components/StatusDot';

const CATEGORIES = [
  { key:'all',     label:'All',            icon:'📦', fn: () => true },
  { key:'compute', label:'Compute',         icon:'🖥',  fn: r => r.type.includes('virtualMachines') || r.type.includes('disks') },
  { key:'aks',     label:'Kubernetes',      icon:'⎈',  fn: r => r.type.includes('managedClusters') },
  { key:'storage', label:'Storage',         icon:'🪣',  fn: r => r.type.includes('Storage') },
  { key:'web',     label:'App Services',    icon:'🌐',  fn: r => r.type.includes('sites') },
  { key:'data',    label:'Databases',       icon:'🗄',  fn: r => r.type.includes('Sql') || r.type.includes('PostgreSQL') },
  { key:'network', label:'Networking',      icon:'🌍',  fn: r => r.type.includes('publicIP') || r.type.includes('network') },
  { key:'security',label:'Security',        icon:'🔑',  fn: r => r.type.includes('KeyVault') },
];

const WASTE = r => r.status === 'Unattached' || r.status === 'Unassigned' || r.status === 'Stopped';

export default function Resources() {
  const [category, setCategory] = useState('all');
  const [subFilter, setSubFilter] = useState('all');
  const [search, setSearch]     = useState('');
  const [wasteOnly, setWasteOnly] = useState(false);
  const [sortBy, setSortBy]     = useState('cost');

  const filtered = useMemo(() => {
    const cat = CATEGORIES.find(c => c.key === category);
    return mockResources
      .filter(r => cat.fn(r))
      .filter(r => subFilter === 'all' || r.sub === subFilter)
      .filter(r => !wasteOnly || WASTE(r))
      .filter(r => !search || r.name.toLowerCase().includes(search.toLowerCase()) || r.rg.toLowerCase().includes(search.toLowerCase()))
      .sort((a,b) => sortBy === 'cost' ? b.cost - a.cost : a.name.localeCompare(b.name));
  }, [category, subFilter, search, wasteOnly, sortBy]);

  const totalCost  = filtered.reduce((s,r)=>s+r.cost,0);
  const wasteCount = mockResources.filter(WASTE).length;
  const wasteCost  = mockResources.filter(WASTE).reduce((s,r)=>s+r.cost,0);

  const subName = id => mockSubscriptions.find(s=>s.id===id)?.name || id;
  const typeName = t => t.split('/').pop();

  const LOC_BADGE = { 'canadacentral':'badge-blue', 'eastus':'badge-green' };

  return (
    <div>
      <div className="page-header">
        <h1>Resource Inventory</h1>
        <p>{mockResources.length} resources across {mockSubscriptions.length} subscriptions</p>
      </div>

      <div className="stat-row">
        <div className="stat-card">
          <span className="stat-icon">📦</span>
          <div className="stat-label">Total Resources</div>
          <div className="stat-value blue">{mockResources.length}</div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">💰</span>
          <div className="stat-label">Filtered Cost/mo</div>
          <div className="stat-value">${totalCost.toLocaleString()}</div>
        </div>
        <div className="stat-card" style={{ border: wasteCount ? '1.5px solid #f9d0d0' : undefined }}>
          <span className="stat-icon">⚠️</span>
          <div className="stat-label">Waste / Idle</div>
          <div className="stat-value orange">{wasteCount}</div>
          <div className="stat-sub">~${wasteCost}/mo savings</div>
        </div>
        <div className="stat-card">
          <span className="stat-icon">🌍</span>
          <div className="stat-label">Locations</div>
          <div className="stat-value">{[...new Set(mockResources.map(r=>r.location))].length}</div>
        </div>
      </div>

      {/* Waste alert */}
      {wasteCount > 0 && (
        <div style={{ background:'#fff4ce', border:'1px solid #f9d0a0', borderLeft:'4px solid #d67f00', borderRadius:8, padding:'12px 16px', marginBottom:20, display:'flex', alignItems:'center', gap:10 }}>
          <span style={{ fontSize:'1.1rem' }}>⚠️</span>
          <div>
            <strong style={{ color:'#7a4a00' }}>Optimization Opportunity</strong>
            <span style={{ color:'#7a4a00', fontSize:'0.85rem', marginLeft:8 }}>
              {wasteCount} idle/unattached resources found. Estimated savings: <strong>${wasteCost}/mo</strong>
            </span>
          </div>
          <button className="btn btn-secondary" style={{ marginLeft:'auto', fontSize:'0.8rem' }} onClick={() => setWasteOnly(v=>!v)}>
            {wasteOnly ? 'Show All' : 'Show Waste Only'}
          </button>
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
            {CATEGORIES.map(c => (
              <button key={c.key}
                className={`btn btn-secondary${category===c.key?' active':''}`}
                onClick={() => setCategory(c.key)}
                style={{ fontSize:'0.8rem', padding:'6px 12px' }}>
                {c.icon} {c.label}
              </button>
            ))}
          </div>
        </div>
        <div className="card-body">
          <div className="controls" style={{ marginBottom:14 }}>
            <input type="text" placeholder="🔍  Search name or resource group…" value={search}
              onChange={e=>setSearch(e.target.value)} style={{ width:280 }} />
            <select value={subFilter} onChange={e=>setSubFilter(e.target.value)}>
              <option value="all">All Subscriptions</option>
              {mockSubscriptions.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <select value={sortBy} onChange={e=>setSortBy(e.target.value)}>
              <option value="cost">Sort by Cost</option>
              <option value="name">Sort by Name</option>
            </select>
            <span className="badge badge-blue">{filtered.length} resources</span>
            <span className="badge badge-gray">${totalCost.toLocaleString()}/mo</span>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Name</th><th>Type</th><th>SKU</th>
                  <th>Location</th><th>Resource Group</th>
                  <th>Subscription</th><th>Status</th>
                  <th style={{ textAlign:'right' }}>Cost/mo</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r,i) => (
                  <tr key={i} style={{ background: WASTE(r) ? '#fffbf0' : undefined }}>
                    <td><strong>{r.name}</strong></td>
                    <td><span className="badge badge-blue" style={{ fontSize:'0.7rem' }}>{typeName(r.type)}</span></td>
                    <td style={{ fontSize:'0.78rem', color:'#5a6070' }}>{r.sku}</td>
                    <td><span className={`badge ${LOC_BADGE[r.location]||'badge-gray'}`} style={{ fontSize:'0.7rem' }}>{r.location}</span></td>
                    <td style={{ fontSize:'0.78rem', color:'#5a6070' }}>{r.rg}</td>
                    <td><span className="badge badge-gray" style={{ fontSize:'0.7rem' }}>{subName(r.sub)}</span></td>
                    <td><StatusDot status={r.status} /></td>
                    <td style={{ textAlign:'right', fontWeight:600, color: r.cost > 500 ? '#c0392b' : '#1a1d29' }}>${r.cost}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {filtered.length === 0 && (
            <div className="empty-state">
              <div className="empty-icon">🔍</div>
              <p>No resources match the current filters.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
