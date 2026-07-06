import React, { useState, useContext, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Tag, AlertTriangle, CheckCircle2, Wrench, Info, RefreshCw } from 'lucide-react';
import { AppCtx } from '../App';
import PageHeader from '../components/PageHeader';
import { SubscriptionRequired, LoadingState, ErrorState } from '../components/QueryStates';
import { fetchResources, patchResourceTags } from '../api/azure';

const REQUIRED_TAGS = ['env', 'owner', 'cost-center', 'project'];

function compliance(tags) {
  const t       = tags || {};
  const missing = REQUIRED_TAGS.filter(k => !t[k]);
  const score   = Math.round(((REQUIRED_TAGS.length - missing.length) / REQUIRED_TAGS.length) * 100);
  return { missing, score };
}

/** Flatten tags from Azure ARM shape ({ tagName, tagValue }[]) or plain object */
function normaliseTags(raw) {
  if (!raw) return {};
  if (Array.isArray(raw)) {
    return Object.fromEntries(raw.map(t => [t.tagName || t.key, t.tagValue || t.value]));
  }
  return raw;
}

export default function TagCompliancePage() {
  const { subscription }   = useContext(AppCtx);
  const qc                 = useQueryClient();
  const [selected, setSelected] = useState(new Set());
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState(null);
  const [appliedIds, setAppliedIds] = useState(new Set());

  // Fetch all VMs + disks + storage as a representative sample
  const { data: rawVms = [],     isLoading: l1, isError: e1 } = useQuery({
    queryKey: ['tag-compliance-vms', subscription],
    queryFn:  () => fetchResources('/resources/vms',     { subscription_id: subscription }),
    enabled:  !!subscription,
    staleTime: 5 * 60_000,
  });
  const { data: rawDisks = [],   isLoading: l2, isError: e2 } = useQuery({
    queryKey: ['tag-compliance-disks', subscription],
    queryFn:  () => fetchResources('/resources/disks',   { subscription_id: subscription }),
    enabled:  !!subscription,
    staleTime: 5 * 60_000,
  });
  const { data: rawStorage = [], isLoading: l3, isError: e3 } = useQuery({
    queryKey: ['tag-compliance-storage', subscription],
    queryFn:  () => fetchResources('/resources/storage', { subscription_id: subscription }),
    enabled:  !!subscription,
    staleTime: 5 * 60_000,
  });

  const isLoading = l1 || l2 || l3;
  const isError   = e1 || e2 || e3;

  const resources = useMemo(() => [
    ...rawVms    .map(r => ({ ...r, _type: 'VM' })),
    ...rawDisks  .map(r => ({ ...r, _type: 'Disk' })),
    ...rawStorage.map(r => ({ ...r, _type: 'Storage' })),
  ].map(r => ({
    id:   r.id || r.resource_id || r.name,
    name: r.name || r.resource_name || r.id,
    type: r._type,
    rg:   r.resource_group || r.resourceGroup || '—',
    tags: normaliseTags(r.tags),
    _raw: r,
  })), [rawVms, rawDisks, rawStorage]);

  const toggle    = (id) => setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const toggleAll = () => setSelected(prev => prev.size === resources.length ? new Set() : new Set(resources.map(r => r.id)));

  const DEFAULT_TAG_VALUES = { env: 'unknown', owner: 'platform-team', 'cost-center': 'CC-000', project: 'untagged' };

  const applyTags = async () => {
    setApplying(true);
    setApplyError(null);
    const ids     = [...selected];
    const errors  = [];
    for (const id of ids) {
      const resource = resources.find(r => r.id === id);
      if (!resource) continue;
      const { missing } = compliance(resource.tags);
      if (!missing.length) continue;
      const patch = Object.fromEntries(missing.map(k => [k, DEFAULT_TAG_VALUES[k]]));
      try {
        await patchResourceTags({
          subscription_id: subscription,
          resource_id:     id,
          tags:            { ...resource.tags, ...patch },
        });
      } catch (err) {
        errors.push(resource.name);
      }
    }
    if (errors.length) {
      setApplyError(`Failed to tag: ${errors.join(', ')}`);
    }
    setAppliedIds(prev => new Set([...prev, ...ids]));
    setSelected(new Set());
    setApplying(false);
    qc.invalidateQueries(['tag-compliance-vms', subscription]);
    qc.invalidateQueries(['tag-compliance-disks', subscription]);
    qc.invalidateQueries(['tag-compliance-storage', subscription]);
  };

  const nonCompliant = resources.filter(r => compliance(r.tags).score < 100);
  const avgScore = resources.length
    ? Math.round(resources.reduce((s, r) => s + compliance(r.tags).score, 0) / resources.length)
    : 0;

  return (
    <div className="page-shell tag-compliance-page">
      <PageHeader title="Tag Compliance" subtitle="Enforce required tags across Azure resources">
        <button className="btn btn-sm btn-ghost" onClick={() => {
          qc.invalidateQueries(['tag-compliance-vms', subscription]);
          qc.invalidateQueries(['tag-compliance-disks', subscription]);
          qc.invalidateQueries(['tag-compliance-storage', subscription]);
        }} title="Refresh">
          <RefreshCw size={13} /> Refresh
        </button>
      </PageHeader>

      {!subscription && <SubscriptionRequired />}
      {subscription && isLoading && <LoadingState message="Loading resources…" />}
      {subscription && isError   && <ErrorState message="Failed to load resources." />}
      {subscription && !isLoading && !isError && (
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
              <div className="stat-label">Total Resources Checked</div>
              <div className="stat-value">{resources.length}</div>
            </div>
          </div>

          {applyError && (
            <div className="alert alert--error" style={{ marginBottom: '0.75rem' }}>
              <AlertTriangle size={14} /> {applyError}
            </div>
          )}

          {selected.size > 0 && (
            <div className="bulk-action-bar" style={{ marginBottom: '0.85rem' }}>
              <span className="bulk-action-bar__count">{selected.size} selected</span>
              <button className="btn btn-sm btn-primary" onClick={applyTags} disabled={applying}>
                <Wrench size={13} /> {applying ? 'Applying…' : 'Auto-fix missing tags'}
              </button>
              <button className="btn btn-sm btn-ghost" onClick={() => setSelected(new Set())}>Clear</button>
            </div>
          )}

          {resources.length === 0 ? (
            <div className="empty-state"><Tag size={28} /><p>No resources found. Sync resources first.</p></div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th><input type="checkbox" checked={selected.size === resources.length && resources.length > 0} onChange={toggleAll} /></th>
                    <th>Resource</th><th>Type</th><th>Resource Group</th>
                    {REQUIRED_TAGS.map(t => <th key={t}><Tag size={10} /> {t}</th>)}
                    <th>Score</th>
                  </tr>
                </thead>
                <tbody>
                  {resources.map(r => {
                    const { missing, score } = compliance(r.tags);
                    const isApplied = appliedIds.has(r.id);
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
          )}

          <div className="tag-hint">
            <Info size={13} />
            Required tags: {REQUIRED_TAGS.map(t => <code key={t}>{t}</code>)}.
            Select non-compliant resources and click <strong>Auto-fix</strong> to apply default placeholder values via the Azure API.
          </div>
        </>
      )}
    </div>
  );
}
