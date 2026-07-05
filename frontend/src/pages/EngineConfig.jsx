import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import usePersistedState from '../hooks/usePersistedState';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Save, Trash2, ChevronDown, ChevronRight, Search, AlertTriangle, WifiOff, Plus } from 'lucide-react';
import api from '../api/client';
import {
  fetchRules,
  fetchRulesByComponent,
  fetchProfiles,
  fetchProfileConfig,
  deleteProfileConfig,
  fetchMetricsTriggers,
  reanalyzeAfterRuleConfig,
} from '../api/azure';
import { resolveComponents, groupRulesByComponent, STATIC_RULES } from '../data/rulesCatalog';
import PageHeader from '../components/PageHeader';
import PageHero from '../components/layout/PageHero';
import OptimizationHubLinks from '../components/navigation/OptimizationHubLinks';
import Toggle from '../components/Toggle';
import AssetIcon from '../components/AssetIcon';
import { PAGE_ICONS, iconForComponent } from '../config/assetIcons';
import { engineComponentSectionId } from '../utils/engineRoutes';

function configArrayToEdits(rows) {
  if (!Array.isArray(rows)) return {};
  return rows.reduce((acc, row) => {
    acc[row.rule_id] = {
      enabled: row.enabled !== false,
      overrides: row.overrides || {},
    };
    return acc;
  }, {});
}

function SettingInput({ setting, value, onChange }) {
  const def = setting.default;
  const current = value !== undefined ? value : def;

  if (setting.type === 'boolean') {
    return <Toggle checked={!!current} onChange={onChange} />;
  }
  if (setting.type === 'select') {
    const options = setting.options || [];
    return (
      <select
        value={current ?? def ?? ''}
        onChange={e => onChange(e.target.value)}
      >
        {options.map(opt => (
          <option key={opt} value={opt}>{opt.charAt(0) + opt.slice(1).toLowerCase()}</option>
        ))}
      </select>
    );
  }
  if (setting.type === 'list') {
    const text = Array.isArray(current) ? current.join(', ') : String(current ?? '');
    return (
      <input
        type="text"
        value={text}
        placeholder="Comma-separated values"
        onChange={e => onChange(e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
      />
    );
  }
  if (setting.type === 'string') {
    return (
      <input
        type="text"
        value={current ?? ''}
        placeholder={setting.placeholder || ''}
        onChange={e => onChange(e.target.value)}
      />
    );
  }
  return (
    <input
      type="number"
      step="any"
      value={current ?? ''}
      onChange={e => onChange(parseFloat(e.target.value))}
    />
  );
}

function RuleCard({ rule, edit, onEdit, onReset, isResetting, metricTriggers = [] }) {
  const ruleEdit = edit || { enabled: rule.enabled, overrides: {} };
  const hasOverride = edit && (
    Object.keys(edit.overrides || {}).length > 0 || edit.enabled !== rule.enabled
  );

  return (
    <article className={`rule-card${ruleEdit.enabled === false ? ' rule-card--disabled' : ''}`}>
      <div className="rule-card__header">
        <div>
          <div className="rule-card__meta">
            <AssetIcon src={iconForComponent(rule.component)} size={16} alt="" />
            <span className="rule-card__name">{rule.name}</span>
            <span className={`badge badge-${(rule.severity || '').toLowerCase()}`}>{rule.severity}</span>
            <span className="badge badge-engine">{rule.engine}</span>
            <span className="rule-card__id">{rule.id}</span>
          </div>
          <p className="rule-card__desc">{rule.description}</p>
        </div>
        <div className="rule-card__actions">
          <Toggle
            checked={ruleEdit.enabled !== false}
            onChange={checked => onEdit({ ...ruleEdit, enabled: checked })}
            label="Enabled"
          />
          {hasOverride && onReset && (
            <button
              type="button"
              className="btn btn-danger btn-sm"
              disabled={isResetting}
              onClick={() => onReset(rule.id)}
            >
              <Trash2 size={12} /> Reset
            </button>
          )}
        </div>
      </div>

      {rule.settings?.length > 0 ? (
        <div className="settings-grid">
          {rule.settings.map(setting => {
            const overrideVal = ruleEdit.overrides?.[setting.key];
            const isOverridden = overrideVal !== undefined
              && JSON.stringify(overrideVal) !== JSON.stringify(setting.default);
            return (
              <div
                key={setting.key}
                className={`setting-field${isOverridden ? ' setting-field--overridden' : ''}`}
              >
                <div className="setting-field__label">
                  {setting.label}
                  {setting.unit && <span className="setting-field__unit"> ({setting.unit})</span>}
                </div>
                <SettingInput
                  setting={setting}
                  value={overrideVal}
                  onChange={val => onEdit({
                    ...ruleEdit,
                    overrides: { ...(ruleEdit.overrides || {}), [setting.key]: val },
                  })}
                />
                <div className="setting-field__default">
                  Default: {Array.isArray(setting.default) ? setting.default.join(', ') : String(setting.default)}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="rule-card__empty">Enable or disable this rule, or adjust severity below.</p>
      )}

      {metricTriggers.length > 0 && (
        <div className="rule-card__triggers">
          <strong>Input metrics:</strong>{' '}
          {metricTriggers.map((t) => t.fact_key).join(', ')}
          <span> · Thresholds and cost/performance effects: docs/METRICS_AND_TRIGGERS.md</span>
        </div>
      )}
    </article>
  );
}

async function fetchRulesCatalog() {
  try {
    const grouped = await fetchRulesByComponent();
    if (Array.isArray(grouped) && grouped.length > 0) {
      return { components: grouped, source: 'api', offline: false };
    }
  } catch { /* fallback */ }
  try {
    const flat = await fetchRules();
    if (Array.isArray(flat) && flat.length > 0) {
      return { components: groupRulesByComponent(flat), source: 'api', offline: false };
    }
  } catch { /* fallback */ }
  return { components: resolveComponents(null), source: 'static', offline: true };
}

export default function EngineConfig() {
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const focusComponent = searchParams.get('component');
  const scrolledRef = useRef(false);
  const [profile, setProfile] = useState('default');
  const [newProf, setNewProf] = useState('');
  const [edits, setEdits] = useState({});
  const [saved, setSaved] = useState(false);
  const [reanalyzing, setReanalyzing] = useState(false);
  const [reanalyzeNote, setReanalyzeNote] = useState('');
  const [search, setSearch] = useState('');
  const [engineFilter, setEngineFilter] = useState('all');
  const [collapsed, setCollapsed] = usePersistedState('finops-engine-collapsed', {});

  const { data: catalog, isLoading, refetch } = useQuery({
    queryKey: ['rules-catalog'],
    queryFn: fetchRulesCatalog,
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const { data: triggersCatalog } = useQuery({
    queryKey: ['metrics-triggers'],
    queryFn: fetchMetricsTriggers,
    staleTime: 10 * 60_000,
    retry: 1,
  });

  const triggersByRule = useMemo(() => {
    const map = new Map();
    const triggers = triggersCatalog?.triggers || {};
    Object.values(triggers).forEach((trigger) => {
      (trigger.rules || []).forEach((ruleId) => {
        if (!map.has(ruleId)) map.set(ruleId, []);
        map.get(ruleId).push(trigger);
      });
    });
    return map;
  }, [triggersCatalog]);

  const components = catalog?.components ?? resolveComponents(null);
  const backendOffline = !isLoading && catalog?.offline === true;
  const standardCount = components.reduce(
    (n, c) => n + (c.rules || []).filter(r => r.engine === 'standard').length,
    0,
  );
  const extendedCount = components.reduce(
    (n, c) => n + (c.rules || []).filter(r => r.engine === 'extended').length,
    0,
  );
  const costExportCount = components.reduce(
    (n, c) => n + (c.rules || []).filter(r => r.engine === 'cost_export').length,
    0,
  );

  const { data: profileData } = useQuery({
    queryKey: ['profiles'],
    queryFn: fetchProfiles,
    retry: 1,
  });
  const { data: config } = useQuery({
    queryKey: ['config', profile],
    queryFn: () => fetchProfileConfig(profile),
    enabled: !!profile && !backendOffline,
    retry: 1,
  });

  const profileList = profileData?.profiles || [];
  const totalRules = components.reduce((n, c) => n + (c.rule_count || c.rules?.length || 0), 0)
    || STATIC_RULES.length;

  useEffect(() => {
    if (config) setEdits(configArrayToEdits(config));
  }, [config]);

  useEffect(() => {
    if (!focusComponent || isLoading) return;
    setCollapsed((prev) => ({ ...prev, [focusComponent]: false }));
    scrolledRef.current = false;
  }, [focusComponent, isLoading, setCollapsed]);

  const saveMut = useMutation({
    mutationFn: async () => {
      const allRuleIds = new Set(components.flatMap(c => (c.rules || []).map(r => r.id)));
      await Promise.all(
        Object.entries(edits)
          .filter(([id]) => allRuleIds.has(id))
          .map(([rule_id, { enabled, overrides }]) =>
            api.post(`/optimize/config/${profile}`, {
              rule_id,
              enabled: enabled !== false,
              overrides: overrides || {},
            })
          )
      );
    },
    onSuccess: async () => {
      setSaved(true);
      qc.invalidateQueries({ queryKey: ['config'] });
      setReanalyzing(true);
      setReanalyzeNote('');
      try {
        const result = await reanalyzeAfterRuleConfig(profile);
        setReanalyzeNote(result?.message || 'Recommendations are refreshing in the background.');
      } catch (err) {
        setReanalyzeNote(
          err?.response?.data?.detail || 'Saved, but background refresh could not be started.',
        );
      } finally {
        setReanalyzing(false);
        setTimeout(() => setSaved(false), 2500);
      }
    },
  });

  const delMut = useMutation({
    mutationFn: rid => deleteProfileConfig(profile, rid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['config'] }),
  });

  const allProfiles = [...new Set([
    ...profileList, 'default', 'aggressive', 'conservative', newProf,
  ].filter(Boolean))];

  const filteredComponents = useMemo(() => {
    const q = search.trim().toLowerCase();
    let groups = components;
    if (focusComponent) {
      groups = groups.filter((g) => g.component === focusComponent);
    }
    return groups
      .map(group => ({
        ...group,
        rules: (group.rules || []).filter(r => {
          if (engineFilter !== 'all' && r.engine !== engineFilter) return false;
          if (!q) return true;
          return (
            r.name.toLowerCase().includes(q) ||
            r.id.toLowerCase().includes(q) ||
            (r.description || '').toLowerCase().includes(q) ||
            group.component.toLowerCase().includes(q)
          );
        }),
      }))
      .filter(g => g.rules.length > 0);
  }, [components, search, engineFilter, focusComponent]);

  useEffect(() => {
    if (!focusComponent || isLoading || scrolledRef.current) return;
    const sectionId = engineComponentSectionId(focusComponent);
    const timer = window.setTimeout(() => {
      document.getElementById(sectionId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      scrolledRef.current = true;
    }, 120);
    return () => window.clearTimeout(timer);
  }, [focusComponent, isLoading, filteredComponents.length]);

  return (
    <div className="page-shell engine-config-page">
      <PageHeader
        title="Optimization rules"
        iconSrc={PAGE_ICONS.engine}
        subtitle="Configure detection thresholds and enable or disable rules per profile."
        badge={catalog?.source === 'api' ? (
          <span className="status-pill status-pill--live">Live</span>
        ) : !isLoading ? (
          <span className="status-pill">Offline catalog</span>
        ) : null}
      >
        {saved && <span className="text-success" style={{ fontSize: '0.84rem', fontWeight: 600 }}>Saved</span>}
        {reanalyzing && (
          <span style={{ fontSize: '0.84rem', color: 'var(--text2)' }}>Refreshing recommendations…</span>
        )}
        {!reanalyzing && reanalyzeNote && (
          <span style={{ fontSize: '0.84rem', color: 'var(--text2)', maxWidth: 280 }}>{reanalyzeNote}</span>
        )}
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => saveMut.mutate()}
          disabled={saveMut.isPending || backendOffline}
        >
          <Save size={15} />
          {saveMut.isPending ? 'Saving…' : 'Save profile'}
        </button>
      </PageHeader>

      <PageHero
        variant="engine-hero"
        eyebrow="Rule engine"
        title={`Profile: ${profile}`}
        subtitle={`${totalRules} rules across ${components.length} components`}
        metrics={[
          { label: 'Total rules', value: totalRules.toLocaleString(), tone: 'default' },
          { label: 'Components', value: components.length.toLocaleString(), tone: 'default' },
          { label: 'Standard', value: standardCount.toLocaleString(), tone: 'default' },
          { label: 'Extended', value: extendedCount.toLocaleString(), tone: 'default' },
          { label: 'Cost export', value: costExportCount.toLocaleString(), tone: 'default' },
        ]}
        actions={[
          { id: 'opt', label: 'Sync center', href: '/admin/optimization' },
          { id: 'recs', label: 'Recommendations', href: '/recommendations' },
        ]}
      />

      <OptimizationHubLinks className="optimization-hub--page" />

      {backendOffline && (
        <div className="alert alert--warning page-section" role="status">
          <WifiOff size={18} className="alert__icon" />
          <div>
            <strong>Backend not connected.</strong> Rules load from the built-in catalog.
            Start the API at <code>127.0.0.1:8000</code> to save profile changes.
            <button type="button" className="btn btn-ghost btn-sm" style={{ marginLeft: 8 }} onClick={() => refetch()}>
              Retry
            </button>
          </div>
        </div>
      )}

      {focusComponent && (
        <div className="alert page-section" role="status">
          <div className="page-callout__row">
            <span>
              Showing rules for <strong>{focusComponent}</strong>
            </span>
            <div className="page-callout__actions">
              <Link to="/admin/optimization" className="btn btn-ghost btn-sm">Back to optimization center</Link>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setSearchParams({})}
              >
                Show all components
              </button>
            </div>
          </div>
        </div>
      )}

      <section className="page-section engine-config-toolbar card">
        <div className="toolbar">
        <span className="toolbar__label">Profile</span>
        <div className="chip-group">
          {allProfiles.map(p => (
            <button
              key={p}
              type="button"
              className={`chip${profile === p ? ' active' : ''}`}
              onClick={() => setProfile(p)}
            >
              {p}
            </button>
          ))}
        </div>
        <div className="toolbar__divider" />
        <input
          type="text"
          placeholder="New profile name"
          value={newProf}
          onChange={e => setNewProf(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && newProf.trim()) {
              setProfile(newProf.trim());
              setNewProf('');
            }
          }}
          style={{ width: 150 }}
        />
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          disabled={!newProf.trim()}
          onClick={() => { setProfile(newProf.trim()); setNewProf(''); }}
        >
          <Plus size={14} /> Add
        </button>
      </div>

      <div className="toolbar">
        <div className="search-field">
          <Search size={15} className="search-field__icon" />
          <input
            type="search"
            placeholder="Search rules or components…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            aria-label="Search rules"
          />
        </div>
        <div className="segmented" role="group" aria-label="Engine filter">
          {[
            { id: 'all', label: 'All' },
            { id: 'standard', label: 'Standard' },
            { id: 'extended', label: 'Extended' },
            { id: 'cost_export', label: 'Cost export' },
          ].map(opt => (
            <button
              key={opt.id}
              type="button"
              className={`segmented__btn${engineFilter === opt.id ? ' active' : ''}`}
              onClick={() => setEngineFilter(opt.id)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>
      </section>

      {isLoading ? (
        <div className="empty-state"><div className="spin" /></div>
      ) : filteredComponents.length === 0 ? (
        <div className="card empty-state">
          <AlertTriangle size={28} />
          <p>No rules match your filters. Clear search or change the engine filter.</p>
        </div>
      ) : (
        filteredComponents.map(group => {
          const isOpen = collapsed[group.component] !== true;
          return (
            <section
              key={group.component}
              id={engineComponentSectionId(group.component)}
              className={`component-section${isOpen ? ' component-section--open' : ''}`}
            >
              <button
                type="button"
                className="component-section__header"
                onClick={() => setCollapsed(prev => ({ ...prev, [group.component]: isOpen }))}
                aria-expanded={isOpen}
              >
                {isOpen ? <ChevronDown size={17} /> : <ChevronRight size={17} />}
                <AssetIcon src={iconForComponent(group.component)} size={18} alt="" />
                <span className="component-section__title">{group.component}</span>
                <span className="badge badge-info">{group.rules.length} rules</span>
              </button>
              {isOpen && (
                <div className="component-section__body">
                  {group.rules.map(rule => (
                    <RuleCard
                      key={rule.id}
                      rule={rule}
                      edit={edits[rule.id]}
                      metricTriggers={triggersByRule.get(rule.id) || []}
                      onEdit={val => setEdits(prev => ({ ...prev, [rule.id]: val }))}
                      onReset={backendOffline ? null : (ruleId => {
                        const next = { ...edits };
                        delete next[ruleId];
                        setEdits(next);
                        delMut.mutate(ruleId);
                      })}
                      isResetting={delMut.isPending}
                    />
                  ))}
                </div>
              )}
            </section>
          );
        })
      )}
    </div>
  );
}
