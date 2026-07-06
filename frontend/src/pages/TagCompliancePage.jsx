import React, { useState, useContext } from 'react';
import { Tag, AlertTriangle, CheckCircle2, Wrench, Download, Info } from 'lucide-react';
import { AppCtx } from '../App';
import PageHeader from '../components/PageHeader';
import { SubscriptionRequired } from '../components/QueryStates';

const REQUIRED_TAGS = ['env', 'owner', 'cost-center', 'project'];

const MOCK_RESOURCES = [
  { id: 1, name: 'vm-prod-api-01',   type: 'VM',   rg: 'rg-prod',    tags: { env: 'prod', owner: 'team-a', 'cost-center': 'CC-101' } },
  { id: 2, name: 'aks-dev-cluster',  type: 'AKS',  rg: 'rg-dev',     tags: { env: 'dev' } },
  { id: 3, name: 'disk-data-03',     type: 'Disk', rg: 'rg-prod',    tags: {} },
  { id: 4, name: 'pip-gateway-01',   type: 'IP',   rg: 'rg-network', tags: { env: 'prod', owner: 'infra', 'cost-center': 'CC-200', project: 'gateway' } },
  { id: 5, name: 'vm-staging-02',    type: 'VM',   rg: 'rg-staging', tags: { env: 'staging', owner: 'team-b' } },
  { id: 6, name: 'storage-backup-1', type: 'Storage', rg: 'rg-backup', tags: { env: 'prod', 'cost-center': 'CC-101' } },
];

function compliance(tags) {
  const missing = REQUIRED_TAGS.filter(t => !tags[t]);
  const score = Math.round(((REQUIRED_TAGS.length - missing.length) / REQUIRED_TAGS.length) * 100);
  return { missing, score };
}

export default function TagCompliancePage() {
  const { subscription } = useContext(AppCtx);
  const [selected, setSelected] = useState(new Set());
  const [tagEdits, setTagEdits] = useState({});
  const [applied, setApplied] = useState(new Set());

  const toggle = (id) => setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleAll = () => setSelected(prev => prev.size === MOCK_RESOURCES.length ? new Set() : new Set(MOCK_RESOURCES.map(r => r.id)));

  const applyTags = () => {
    setApplied(prev => new Set([...prev, ...selected]));
    setSelected(new Set());
  };

  const nonCompliant = MOCK_RESOURCES.filter(r => compliance(r.tags).score < 100);
  const avgScore = Math.round(MOCK_RESOURCES.reduce((s, r) => s + compliance(r.tags).score, 0) / MOCK_RESOURCES.length);

  return (
    <div className="page-shell tag-compliance-page">
      <PageHeader title="Tag Compliance" subtitle="Enforce required tags across all Azure resources" />
      {!subscription && <SubscriptionRequired />}
      {subscription && (
        <>
          <div className="grid-3" style={{ marginBottom: '1.25rem' }}>
            <div className={`stat-card ${avgScore >= 80 ? 'success' : avgScore >= 60 ? 'warning' : 'danger'}`}>
              <div className="stat-label">Avg. Compliance Score</div>
              <div className="stat-value">{avgScore}%</div>
            </div>
            <div className="stat-card warning">
              <div className="stat-label">Non-Compliant Resources</div>
              <div className="stat-value">{nonCompliant.length}</div>
            </div>
            <div className="stat-card accent">
              <div className="stat-label">Required Tags</div>
              <div className="stat-value">{REQUIRED_TAGS.length}</div>
            </div>
          </div>

          {selected.size > 0 && (
            <div className="bulk-action-bar" style={{ marginBottom: '0.85rem' }}>
              <span className="bulk-action-bar__count">{selected.size} selected</span>
              <button className="btn btn-sm btn-primary" onClick={applyTags}>
                <Wrench size={13} /> Auto-fix missing tags
              </button>
              <button className="btn btn-sm btn-ghost" onClick={() => setSelected(new Set())}>Clear</button>
            </div>
          )}

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th><input type="checkbox" checked={selected.size === MOCK_RESOURCES.length} onChange={toggleAll} /></th>
                  <th>Resource</th><th>Type</th><th>Resource Group</th>
                  {REQUIRED_TAGS.map(t => <th key={t}><Tag size={10} /> {t}</th>)}
                  <th>Score</th>
                </tr>
              </thead>
              <tbody>
                {MOCK_RESOURCES.map(r => {
                  const { missing, score } = compliance(r.tags);
                  const isApplied = applied.has(r.id);
                  return (
                    <tr key={r.id} className={isApplied ? 'finding-row--resolved' : ''}>
                      <td><input type="checkbox" checked={selected.has(r.id)} onChange={() => toggle(r.id)} /></td>
                      <td><code>{r.name}</code></td>
                      <td><span className="badge badge-info">{r.type}</span></td>
                      <td style={{ color: 'var(--text3)', fontSize: '0.78rem' }}>{r.rg}</td>
                      {REQUIRED_TAGS.map(t => (
                        <td key={t}>
                          {r.tags[t]
                            ? <span className="tag-cell tag-cell--ok"><CheckCircle2 size={11} /> {r.tags[t]}</span>
                            : isApplied
                              ? <span className="tag-cell tag-cell--fixed"><CheckCircle2 size={11} /> auto-set</span>
                              : <span className="tag-cell tag-cell--missing"><AlertTriangle size={11} /> missing</span>}
                        </td>
                      ))}
                      <td>
                        <div className="score-bar-wrap">
                          <div className="score-bar">
                            <div className="score-bar__fill" style={{ width: `${isApplied ? 100 : score}%`, background: (isApplied || score === 100) ? 'var(--success)' : score >= 50 ? 'var(--warning)' : 'var(--danger)' }} />
                          </div>
                          <span className="score-bar__label">{isApplied ? 100 : score}%</span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="tag-hint">
            <Info size={13} />
            Required tags: {REQUIRED_TAGS.map(t => <code key={t}>{t}</code>)}.
            Select non-compliant resources and click <strong>Auto-fix</strong> to apply default values.
          </div>
        </>
      )}
    </div>
  );
}
