import React, { useState, useMemo } from 'react';
import { mockResources, mockSubscriptions } from '../api/mockData';
import StatusDot  from '../components/StatusDot';
import CostBadge  from '../components/CostBadge';
import EnvBadge   from '../components/EnvBadge';
import AzureIcon  from '../components/AzureIcon';

const CATEGORIES = [
  { key:'all',     label:'All Resources',  icon:'📦', fn:()=>true },
  { key:'compute', label:'Compute',         icon:'🖥',  fn:r=>r.type.includes('virtualMachines')||r.type.includes('disks') },
  { key:'aks',     label:'Kubernetes',      icon:'⎈',  fn:r=>r.type.includes('managedClusters') },
  { key:'storage', label:'Storage',         icon:'🪣',  fn:r=>r.type.includes('Storage') },
  { key:'web',     label:'App Services',    icon:'🌐',  fn:r=>r.type.includes('sites') },
  { key:'data',    label:'Databases',       icon:'🗄',  fn:r=>r.type.includes('Sql')||r.type.includes('PostgreSQL') },
  { key:'network', label:'Networking',      icon:'🌍',  fn:r=>r.type.includes('publicIP') },
  { key:'security',label:'Security',        icon:'🔑',  fn:r=>r.type.includes('KeyVault') },
];

const WASTE = r => ['Unattached','Unassigned','Stopped'].includes(r.status);
const subName = (subs,id) => subs.find(s=>s.id===id)?.name || id;
const subEnv  = (subs,id) => subs.find(s=>s.id===id)?.env  || 'dev';
const LOC_BADGE = { 'canadacentral':'badge-blue','eastus':'badge-green','westus':'badge-orange' };

export default function Resources() {
  const [category, setCategory]   = useState('all');
  const [subFilter, setSubFilter] = useState('all');
  const [search, setSearch]       = useState('');
  const [wasteOnly, setWasteOnly] = useState(false);
  const [sortBy, setSortBy]       = useState('cost');

  const filtered = useMemo(() => {
    const cat = CATEGORIES.find(c=>c.key===category);
    return mockResources
      .filter(r=>cat.fn(r))
      .filter(r=>subFilter==='all'||r.sub===subFilter)
      .filter(r=>!wasteOnly||WASTE(r))
      .filter(r=>!search||
        r.name.toLowerCase().includes(search.toLowerCase())||
        r.rg.toLowerCase().includes(search.toLowerCase())||
        r.type.toLowerCase().includes(search.toLowerCase())
      )
      .sort((a,b)=>sortBy==='cost'?b.cost-a.cost:a.name.localeCompare(b.name));
  }, [category,subFilter,search,wasteOnly,sortBy]);

  const totalCost  = filtered.reduce((s,r)=>s+r.cost,0);
  const wasteItems = mockResources.filter(WASTE);
  const wasteCost  = wasteItems.reduce((s,r)=>s+r.cost,0);

  return (
    <div>
      <div className="page-header">
        <h1>Resource Inventory</h1>
        <p>{mockResources.length} resources · {mockSubscriptions.length} subscriptions · ${mockResources.reduce((s,r)=>s+r.cost,0).toLocaleString()}/mo total</p>
      </div>

      <div className="stat-row">
        <div className="stat-card">
          <div className="stat-icon-wrap" style={{background:'#e8f3fc'}}>📦</div>
          <div className="stat-label">Total Resources</div>
          <div className="stat-value blue">{mockResources.length}</div>
          <div className="stat-sub">{[...new Set(mockResources.map(r=>r.rg))].length} resource groups</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon-wrap" style={{background:'#dff6dd'}}>💰</div>
          <div className="stat-label">Filtered Cost/mo</div>
          <div className="stat-value">${totalCost.toLocaleString()}</div>
          <div className="stat-sub">{filtered.length} resources shown</div>
        </div>
        <div className="stat-card" style={{border:wasteItems.length?'1.5px solid #f9d0d0':undefined}}>
          <div className="stat-icon-wrap" style={{background:'#fff4ce'}}>⚠️</div>
          <div className="stat-label">Waste / Idle</div>
          <div className="stat-value orange">{wasteItems.length}</div>
          <div className="stat-sub">~${wasteCost}/mo savings</div>
        </div>
        <div className="stat-card">
          <div className="stat-icon-wrap" style={{background:'#f3e8ff'}}>📍</div>
          <div className="stat-label">Regions</div>
          <div className="stat-value">{[...new Set(mockResources.map(r=>r.location))].length}</div>
          <div className="stat-sub">Active locations</div>
        </div>
      </div>

      {wasteItems.length > 0 && (
        <div className="alert-banner alert-warning">
          <span style={{fontSize:'1.1rem'}}>⚠️</span>
          <div style={{flex:1}}>
            <strong>Optimization Opportunity Detected</strong>
            <span style={{marginLeft:10,fontSize:'0.84rem'}}>
              {wasteItems.length} idle/unattached resources · Estimated savings <strong>${wasteCost}/mo</strong>
            </span>
          </div>
          <button className="btn btn-sm btn-warning" onClick={()=>setWasteOnly(v=>!v)}>
            {wasteOnly?'Show All':'Review Waste'}
          </button>
        </div>
      )}

      <div className="card">
        <div className="card-header" style={{flexWrap:'wrap',gap:8}}>
          <div style={{display:'flex',gap:6,flexWrap:'wrap'}}>
            {CATEGORIES.map(c=>(
              <button key={c.key}
                className={`btn btn-sm btn-secondary${category===c.key?' active':''}`}
                onClick={()=>setCategory(c.key)}>
                {c.icon} {c.label}
              </button>
            ))}
          </div>
        </div>
        <div className="card-body">
          <div className="toolbar">
            <input type="text" placeholder="🔍  Search name, type, or resource group…"
              value={search} onChange={e=>setSearch(e.target.value)} style={{width:300}} />
            <select value={subFilter} onChange={e=>setSubFilter(e.target.value)}>
              <option value="all">All Subscriptions</option>
              {mockSubscriptions.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <select value={sortBy} onChange={e=>setSortBy(e.target.value)}>
              <option value="cost">Sort: Cost ↓</option>
              <option value="name">Sort: Name A→Z</option>
            </select>
            <span className="badge badge-blue">{filtered.length} results</span>
            <span className="badge badge-gray">${totalCost.toLocaleString()}/mo</span>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th style={{width:36}}></th>
                  <th>Resource Name</th>
                  <th>Type</th>
                  <th>SKU / Tier</th>
                  <th>Location</th>
                  <th>Resource Group</th>
                  <th>Subscription</th>
                  <th>Status</th>
                  <th style={{textAlign:'right'}}>Cost/mo</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r,i)=>(
                  <tr key={i} className={WASTE(r)?'row-warn':''}>
                    <td><AzureIcon type={r.type} size={28} /></td>
                    <td>
                      <div style={{fontWeight:600,color:'#1a1d29',fontSize:'0.85rem'}}>{r.name}</div>
                      <div style={{fontSize:'0.7rem',color:'#9ba3b8',marginTop:1}}>{r.type.split('/')[0]}</div>
                    </td>
                    <td><span className="badge badge-blue" style={{fontSize:'0.68rem'}}>{r.type.split('/').pop()}</span></td>
                    <td style={{fontSize:'0.78rem',color:'#5a6070'}}>{r.sku}</td>
                    <td><span className={`badge ${LOC_BADGE[r.location]||'badge-gray'}`} style={{fontSize:'0.68rem'}}>{r.location}</span></td>
                    <td style={{fontSize:'0.78rem',color:'#5a6070',maxWidth:160,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{r.rg}</td>
                    <td><EnvBadge env={subEnv(mockSubscriptions,r.sub)} /></td>
                    <td><StatusDot status={r.status} /></td>
                    <td style={{textAlign:'right'}}><CostBadge value={r.cost} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filtered.length===0&&(
            <div className="empty-state">
              <div style={{fontSize:'2.5rem',marginBottom:10}}>🔍</div>
              <p>No resources match the current filters.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
