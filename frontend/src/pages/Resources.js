import React, { useState } from 'react';
import { mockResources } from '../api/mockData';

const TABS = [
  { key:'all',     label:'All Resources',  icon:'📦', typeKey: null },
  { key:'vms',     label:'Virtual Machines',icon:'🖥',  typeKey:'virtualMachines' },
  { key:'aks',     label:'AKS Clusters',   icon:'⎈',  typeKey:'managedClusters' },
  { key:'storage', label:'Storage',        icon:'🪣',  typeKey:'storageAccounts' },
  { key:'app',     label:'App Services',   icon:'🌐',  typeKey:'sites' },
  { key:'sql',     label:'SQL Servers',    icon:'🗄',  typeKey:'servers' },
  { key:'disks',   label:'Disks',          icon:'💿',  typeKey:'disks' },
  { key:'kv',      label:'Key Vaults',     icon:'🔑',  typeKey:'vaults' },
  { key:'pip',     label:'Public IPs',     icon:'🌍',  typeKey:'publicIPAddresses' },
];

const LOCATION_COLORS = {
  'canadacentral': 'badge-blue',
  'eastus':        'badge-green',
  'westus':        'badge-orange',
};

export default function Resources() {
  const [active, setActive] = useState('all');
  const [search, setSearch] = useState('');

  const filtered = mockResources.filter(r => {
    const t = TABS.find(t => t.key === active);
    const matchType = !t?.typeKey || r.type.split('/').pop().toLowerCase() === t.typeKey.toLowerCase();
    const matchSearch = !search ||
      r.name.toLowerCase().includes(search.toLowerCase()) ||
      r.location.toLowerCase().includes(search.toLowerCase()) ||
      r.type.toLowerCase().includes(search.toLowerCase());
    return matchType && matchSearch;
  });

  const rg = name => name?.split('/resourceGroups/')[1]?.split('/')[0] || '—';

  return (
    <div>
      <div className="page-header">
        <h1>Resource Inventory</h1>
        <p>{mockResources.length} total resources across your subscription</p>
      </div>

      <div className="stat-row">
        {[['VMs','🖥',2],['AKS','⎈',1],['Storage','🪣',2],['App Services','🌐',2]].map(([l,ic,n]) => (
          <div className="stat-card" key={l}>
            <span className="stat-icon">{ic}</span>
            <div className="stat-label">{l}</div>
            <div className="stat-value">{n}</div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-header">
          <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
            {TABS.map(t => (
              <button key={t.key}
                className={`btn btn-secondary${active===t.key?' active':''}`}
                onClick={() => setActive(t.key)}
                style={{ fontSize:'0.8rem', padding:'6px 12px' }}>
                {t.icon} {t.label}
              </button>
            ))}
          </div>
        </div>
        <div className="card-body">
          <div className="controls">
            <input type="text" placeholder="🔍  Search by name, type, or location…"
              value={search} onChange={e => setSearch(e.target.value)}
              style={{ width:320 }} />
            <span className="badge badge-blue">{filtered.length} results</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Name</th><th>Resource Type</th><th>Location</th><th>Resource Group</th></tr>
              </thead>
              <tbody>
                {filtered.map((item,i) => (
                  <tr key={i}>
                    <td><strong>{item.name}</strong></td>
                    <td><span className="badge badge-blue">{item.type.split('/').pop()}</span></td>
                    <td><span className={`badge ${LOCATION_COLORS[item.location]||'badge-gray'}`}>{item.location}</span></td>
                    <td style={{ color:'#5a6070' }}>{rg(item.id)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filtered.length === 0 && (
            <div className="empty-state">
              <div className="empty-icon">🔍</div>
              <p>No resources match your filter.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
