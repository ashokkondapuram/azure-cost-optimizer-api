import React, { useContext, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Cpu, HardDrive } from 'lucide-react';
import { AppCtx } from '../App';
import { fetchVMs, fetchDisks } from '../api/azure';

const STATE_COLOR = { running: 'var(--success)', stopped: 'var(--warning)', deallocated: 'var(--text3)', starting: 'var(--accent)' };

export default function VirtualMachines() {
  const { subscription } = useContext(AppCtx);
  const [search, setSearch] = useState('');
  const [tab, setTab] = useState('vms');

  const { data: vms = [], isLoading: loadVMs } = useQuery({
    queryKey: ['vms', subscription],
    queryFn: () => fetchVMs({ subscription_id: subscription }),
    enabled: !!subscription,
  });

  const { data: disks = [], isLoading: loadDisks } = useQuery({
    queryKey: ['disks', subscription],
    queryFn: () => fetchDisks({ subscription_id: subscription }),
    enabled: !!subscription,
  });

  const filteredVMs = vms.filter(v =>
    !search || (v.name || '').toLowerCase().includes(search.toLowerCase()) ||
    (v.location || '').toLowerCase().includes(search.toLowerCase())
  );
  const filteredDisks = disks.filter(d =>
    !search || (d.name || '').toLowerCase().includes(search.toLowerCase())
  );

  const unattached = disks.filter(d => (d.properties?.diskState || '') === 'Unattached');
  const running    = vms.filter(v => (v.properties?.instanceView?.statuses || []).some(s => s.code === 'PowerState/running'));
  const totalDisksGB = disks.reduce((s, d) => s + (d.properties?.diskSizeGB || 0), 0);

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Virtual Machines & Disks</div>
          <div className="page-sub">Live from Azure Resource Manager · {vms.length} VMs · {disks.length} disks</div>
        </div>
        <input placeholder="Search name, location…" value={search} onChange={e => setSearch(e.target.value)} style={{ width: 240 }} />
      </div>

      <div className="grid-4" style={{ marginBottom: '1.5rem' }}>
        <div className="stat-card accent">
          <div className="stat-label">Total VMs</div>
          <div className="stat-value">{vms.length}</div>
          <div className="stat-sub">{running.length} running</div>
        </div>
        <div className="stat-card danger">
          <div className="stat-label">Unattached Disks</div>
          <div className="stat-value" style={{ color: 'var(--danger)' }}>{unattached.length}</div>
          <div className="stat-sub">Direct waste</div>
        </div>
        <div className="stat-card warning">
          <div className="stat-label">Total Disks</div>
          <div className="stat-value">{disks.length}</div>
          <div className="stat-sub">{totalDisksGB.toLocaleString()} GB total</div>
        </div>
        <div className="stat-card success">
          <div className="stat-label">Locations</div>
          <div className="stat-value">{[...new Set(vms.map(v => v.location))].length}</div>
          <div className="stat-sub">Unique Azure regions</div>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: '1rem' }}>
        <button className={`btn ${tab === 'vms' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTab('vms')}><Cpu size={14} />VMs ({vms.length})</button>
        <button className={`btn ${tab === 'disks' ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setTab('disks')}><HardDrive size={14} />Disks ({disks.length})</button>
      </div>

      <div className="card">
        {tab === 'vms' && (
          loadVMs ? <div className="empty-state"><div className="spin" /></div> :
          filteredVMs.length === 0 ? <div className="empty-state"><p>No VMs found.</p></div> : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Name</th><th>Size</th><th>Location</th><th>OS</th><th>State</th><th>Resource Group</th><th>Tags</th></tr></thead>
                <tbody>
                  {filteredVMs.map((vm, i) => {
                    const p = vm.properties || {};
                    const statuses = p.instanceView?.statuses || [];
                    const powerState = statuses.find(s => s.code?.startsWith('PowerState/'))?.code?.split('/')[1] || 'unknown';
                    const rg = (vm.id || '').split('/').find((_, idx, arr) => arr[idx-1]?.toLowerCase() === 'resourcegroups') || '';
                    const tags = vm.tags || {};
                    return (
                      <tr key={i}>
                        <td style={{ color: 'var(--text)', fontWeight: 500 }}>{vm.name}</td>
                        <td style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{p.hardwareProfile?.vmSize || '—'}</td>
                        <td>{vm.location}</td>
                        <td>{p.storageProfile?.osDisk?.osType || '—'}</td>
                        <td>
                          <span style={{ color: STATE_COLOR[powerState] || 'var(--text2)', fontWeight: 600, fontSize: '0.8rem', textTransform: 'capitalize' }}>
                            ● {powerState}
                          </span>
                        </td>
                        <td style={{ color: 'var(--text3)' }}>{rg}</td>
                        <td>
                          {Object.entries(tags).slice(0, 3).map(([k, v]) => (
                            <span key={k} className="tag">{k}: {v}</span>
                          ))}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )
        )}
        {tab === 'disks' && (
          loadDisks ? <div className="empty-state"><div className="spin" /></div> :
          filteredDisks.length === 0 ? <div className="empty-state"><p>No disks found.</p></div> : (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Name</th><th>Size</th><th>SKU</th><th>State</th><th>Location</th><th>Resource Group</th></tr></thead>
                <tbody>
                  {filteredDisks.map((d, i) => {
                    const p = d.properties || {};
                    const sku = d.sku?.name || '';
                    const state = p.diskState || 'Unknown';
                    const rg = (d.id || '').split('/').find((_, idx, arr) => arr[idx-1]?.toLowerCase() === 'resourcegroups') || '';
                    return (
                      <tr key={i}>
                        <td style={{ color: state === 'Unattached' ? 'var(--danger)' : 'var(--text)', fontWeight: 500 }}>{d.name}</td>
                        <td>{p.diskSizeGB || '—'} GB</td>
                        <td style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>{sku}</td>
                        <td><span className={`badge ${state === 'Unattached' ? 'badge-critical' : 'badge-low'}`}>{state}</span></td>
                        <td>{d.location}</td>
                        <td style={{ color: 'var(--text3)' }}>{rg}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )
        )}
      </div>
    </div>
  );
}
