import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Settings, Save, Trash2, Plus } from 'lucide-react';
import { fetchRules, fetchProfiles, fetchProfileConfig, upsertProfileConfig, deleteProfileConfig } from '../api/azure';

export default function EngineConfig() {
  const qc = useQueryClient();
  const [profile, setProfile] = useState('default');
  const [newProf, setNewProf] = useState('');
  const [edits, setEdits]     = useState({});
  const [saved, setSaved]     = useState('');

  const { data: rules = [] }    = useQuery({ queryKey: ['rules'],    queryFn: fetchRules });
  const { data: profiles = [] } = useQuery({ queryKey: ['profiles'], queryFn: fetchProfiles });
  const { data: config }        = useQuery({ queryKey: ['config', profile], queryFn: () => fetchProfileConfig(profile), enabled: !!profile });

  useEffect(() => { setEdits(config || {}); }, [config]);

  const saveMut = useMutation({
    mutationFn: () => upsertProfileConfig(profile, edits),
    onSuccess: () => { setSaved('Saved!'); qc.invalidateQueries({ queryKey: ['config'] }); setTimeout(() => setSaved(''), 2500); },
  });
  const delMut = useMutation({
    mutationFn: (rid) => deleteProfileConfig(profile, rid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['config'] }),
  });

  const allProfiles = [...new Set([...(Array.isArray(profiles) ? profiles : []), 'default', 'aggressive', 'conservative', newProf].filter(Boolean))];

  const categories = [...new Set(rules.map(r => r.category))];

  return (
    <div>
      <div className="page-header">
        <div>
          <div className="page-title">Engine Configuration</div>
          <div className="page-sub">Override rule thresholds per profile · applies to all future analysis runs</div>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          {saved && <span style={{ color: 'var(--success)', fontWeight: 600, fontSize: '0.85rem' }}>{saved}</span>}
          <button className="btn btn-primary" onClick={() => saveMut.mutate()} disabled={saveMut.isPending}>
            <Save size={14} />{saveMut.isPending ? 'Saving…' : 'Save Profile'}
          </button>
        </div>
      </div>

      {/* Profile selector */}
      <div style={{ display: 'flex', gap: 10, marginBottom: '1.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <div className="topbar-label">Profile:</div>
        {allProfiles.map(p => (
          <button key={p} className={`btn ${profile === p ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setProfile(p)}>{p}</button>
        ))}
        <input
          placeholder="+ new profile name"
          value={newProf}
          onChange={e => setNewProf(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && newProf.trim()) { setProfile(newProf.trim()); setNewProf(''); } }}
          style={{ width: 180 }}
        />
      </div>

      {/* Rules by category */}
      {categories.map(cat => {
        const catRules = rules.filter(r => r.category === cat);
        return (
          <div key={cat} className="card" style={{ marginBottom: '1.25rem' }}>
            <div style={{ fontWeight: 700, marginBottom: '1rem', fontSize: '0.88rem', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--text3)' }}>{cat}</div>
            <div style={{ display: 'grid', gap: '0.75rem' }}>
              {catRules.map(rule => {
                const override = edits[rule.id] || {};
                const defaults = rule.defaults || {};
                return (
                  <div key={rule.id} style={{ background: 'var(--surface2)', borderRadius: 8, padding: '1rem', border: '1px solid var(--border)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                      <div>
                        <span style={{ fontWeight: 600, fontSize: '0.88rem', color: 'var(--text)' }}>{rule.name}</span>
                        {' '}<span className={`badge badge-${(rule.severity || '').toLowerCase()}`}>{rule.severity}</span>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text3)', marginTop: 3 }}>{rule.description}</div>
                      </div>
                      {edits[rule.id] && (
                        <button className="btn btn-danger" style={{ padding: '3px 8px', fontSize: '0.72rem' }} onClick={() => {
                          const next = { ...edits }; delete next[rule.id]; setEdits(next);
                          delMut.mutate(rule.id);
                        }}><Trash2 size={12} />Reset</button>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                      {Object.entries(defaults).map(([k, defVal]) => (
                        <label key={k} style={{ display: 'flex', flexDirection: 'column', gap: 3, fontSize: '0.78rem', color: 'var(--text3)' }}>
                          {k.replace(/_/g, ' ')}
                          <input
                            type="number"
                            value={override[k] ?? defVal}
                            onChange={e => setEdits(prev => ({ ...prev, [rule.id]: { ...(prev[rule.id] || {}), [k]: parseFloat(e.target.value) } }))}
                            style={{ width: 90 }}
                          />
                        </label>
                      ))}
                      {Object.keys(defaults).length === 0 && <span style={{ fontSize: '0.78rem', color: 'var(--text3)' }}>No configurable thresholds</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
