import React, { useState, useContext } from 'react';
import { GitCompare, Tag, Cpu, HardDrive, Clock, AlertCircle } from 'lucide-react';
import { AppCtx } from '../App';
import PageHeader from '../components/PageHeader';
import { SubscriptionRequired } from '../components/QueryStates';

const MOCK_DRIFT = [
  {
    id: 1,
    resource: 'vm-prod-api-01',
    type: 'VirtualMachine',
    field: 'VM SKU',
    before: 'Standard_D4s_v3',
    after: 'Standard_D8s_v3',
    changed_by: 'ops-team@corp.com',
    detected_at: '2026-07-04 14:22',
    severity: 'high',
  },
  {
    id: 2,
    resource: 'aks-prod-cluster',
    type: 'AKS',
    field: 'Node count',
    before: '3',
    after: '8',
    changed_by: 'deploy-pipeline',
    detected_at: '2026-07-04 09:10',
    severity: 'medium',
  },
  {
    id: 3,
    resource: 'vm-staging-02',
    type: 'VirtualMachine',
    field: 'Tags',
    before: 'env=staging',
    after: 'env=staging, owner=team-b',
    changed_by: 'azureuser',
    detected_at: '2026-07-03 17:55',
    severity: 'low',
  },
  {
    id: 4,
    resource: 'disk-data-03',
    type: 'Disk',
    field: 'SKU',
    before: 'Premium_LRS',
    after: 'UltraSSD_LRS',
    changed_by: 'infra-bot',
    detected_at: '2026-07-02 11:30',
    severity: 'high',
  },
];

const SEV_ICON = { high: <AlertCircle size={14} className="text-danger" />, medium: <AlertCircle size={14} className="text-warning" />, low: <AlertCircle size={14} className="text-success" /> };

export default function DriftDetection() {
  const { subscription } = useContext(AppCtx);
  const [search, setSearch] = useState('');
  const [sev, setSev] = useState('all');

  const rows = MOCK_DRIFT.filter(r =>
    (sev === 'all' || r.severity === sev) &&
    (r.resource.toLowerCase().includes(search.toLowerCase()) || r.field.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="page-shell drift-page">
      <PageHeader title="Drift Detection" subtitle="Resources that changed between analysis runs" />

      {!subscription && <SubscriptionRequired message="Select a subscription." />}

      {subscription && (
        <>
          <div className="grid-4" style={{ marginBottom: '1.25rem' }}>
            {['high','medium','low'].map(s => (
              <div key={s} className={`stat-card ${s === 'high' ? 'danger' : s === 'medium' ? 'warning' : 'success'}`}>
                <div className="stat-label">{s.charAt(0).toUpperCase()+s.slice(1)} Drift</div>
                <div className="stat-value">{MOCK_DRIFT.filter(r => r.severity === s).length}</div>
              </div>
            ))}
            <div className="stat-card accent">
              <div className="stat-label">Total Changes</div>
              <div className="stat-value">{MOCK_DRIFT.length}</div>
            </div>
          </div>

          <div className="toolbar">
            <div className="search-field">
              <span className="search-field__icon"><GitCompare size={14} /></span>
              <input placeholder="Search resource or field…" value={search} onChange={e => setSearch(e.target.value)} />
            </div>
            <span className="toolbar__divider" />
            {['all','high','medium','low'].map(s => (
              <button key={s} type="button" className={`chip${sev === s ? ' active' : ''}`} onClick={() => setSev(s)}>
                {s.charAt(0).toUpperCase()+s.slice(1)}
              </button>
            ))}
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Resource</th><th>Type</th><th>Field Changed</th>
                  <th>Before</th><th>After</th>
                  <th>Changed By</th><th>Detected</th><th>Severity</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.id}>
                    <td><code>{r.resource}</code></td>
                    <td><span className="badge badge-info">{r.type}</span></td>
                    <td>{r.field}</td>
                    <td className="drift-cell drift-cell--before">{r.before}</td>
                    <td className="drift-cell drift-cell--after">{r.after}</td>
                    <td>{r.changed_by}</td>
                    <td><span className="icon-inline"><Clock size={11} />{r.detected_at}</span></td>
                    <td>
                      <span className={`badge badge-${r.severity === 'high' ? 'critical' : r.severity === 'medium' ? 'medium' : 'low'}`}>
                        {SEV_ICON[r.severity]} {r.severity}
                      </span>
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={8} className="empty-state" style={{ padding: '2rem', textAlign: 'center' }}>No drift detected matching filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
