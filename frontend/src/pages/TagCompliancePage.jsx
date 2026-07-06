/**
 * Tag Compliance Scorecard page
 *
 * Layout:
 *  ┌─ Overall score gauge + KPI bar ────────────────────────────┐
 *  ├─ Per-tag coverage bar chart (CSS bars) ────────────────────┤
 *  ├─ Per-resource-group compliance table (worst first) ────────┤
 *  └─ Non-compliant resources table (filterable + paginated) ───┘
 *
 * Data sources:
 *   GET /tag-compliance/score/{subscriptionId}
 *   GET /tag-compliance/groups/{subscriptionId}
 */

import React, { useState, useMemo, useCallback, useContext } from 'react';
import { RefreshCw, Tag, CheckCircle, XCircle, ChevronUp, ChevronDown, AlertTriangle, Plus, X } from 'lucide-react';
import { fetchComplianceScore, fetchComplianceGroups } from '../api/tagCompliance';

let SubscriptionContext;
try { ({ SubscriptionContext } = require('../context/SubscriptionContext')); } catch { SubscriptionContext = null; }
function useCtxSub() {
  const ctx = SubscriptionContext ? useContext(SubscriptionContext) : null; // eslint-disable-line
  return ctx?.subscriptionId ?? ctx?.activeSubscription ?? null;
}

// ── helpers ────────────────────────────────────────────────────────────────
const DEFAULT_TAGS = ['environment', 'owner', 'cost-center'];

function scoreColour(pct) {
  if (pct === null || pct === undefined) return { ring: 'stroke-gray-300', text: 'text-gray-400', badge: 'bg-gray-100 text-gray-500' };
  if (pct >= 90) return { ring: 'stroke-teal-500', text: 'text-teal-600 dark:text-teal-400', badge: 'bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300' };
  if (pct >= 70) return { ring: 'stroke-amber-400', text: 'text-amber-600 dark:text-amber-400', badge: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' };
  return { ring: 'stroke-red-500', text: 'text-red-600 dark:text-red-400', badge: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' };
}

function Skeleton({ className = '' }) {
  return <div className={`animate-pulse rounded bg-gray-200 dark:bg-gray-700 ${className}`} />;
}

// ── Score gauge (SVG circle) ───────────────────────────────────────────────
function ScoreGauge({ pct, loading }) {
  const R = 52;
  const CIRC = 2 * Math.PI * R;
  const filled = pct != null ? (pct / 100) * CIRC : 0;
  const colours = scoreColour(pct);

  if (loading) return <Skeleton className="w-36 h-36 rounded-full mx-auto" />;

  return (
    <div className="flex flex-col items-center">
      <svg width="140" height="140" viewBox="0 0 140 140" className="-rotate-90">
        <circle cx="70" cy="70" r={R} fill="none" stroke="currentColor" strokeWidth="12" className="text-gray-200 dark:text-gray-700" />
        <circle
          cx="70" cy="70" r={R} fill="none"
          strokeWidth="12"
          strokeDasharray={`${filled} ${CIRC}`}
          strokeLinecap="round"
          className={`transition-all duration-700 ${colours.ring}`}
        />
      </svg>
      <div className="-mt-[100px] mb-[60px] text-center pointer-events-none">
        <p className={`text-3xl font-bold tabular-nums ${colours.text}`}>
          {pct != null ? `${pct}%` : '—'}
        </p>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">compliance</p>
      </div>
    </div>
  );
}

// ── Per-tag coverage bars ──────────────────────────────────────────────────
function TagCoverageBars({ tagCoverage, loading }) {
  if (loading) return <Skeleton className="h-32 rounded-xl" />;
  if (!tagCoverage || Object.keys(tagCoverage).length === 0) return null;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm p-4">
      <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-3">Coverage per required tag</h3>
      <div className="space-y-3">
        {Object.entries(tagCoverage).map(([tag, pct]) => {
          const c = scoreColour(pct);
          return (
            <div key={tag}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-mono font-medium text-gray-700 dark:text-gray-300">{tag}</span>
                <span className={`text-xs font-semibold tabular-nums ${c.text}`}>{pct}%</span>
              </div>
              <div className="w-full bg-gray-100 dark:bg-gray-700 rounded-full h-2.5 overflow-hidden">
                <div
                  className="h-2.5 rounded-full transition-all duration-500"
                  style={{
                    width: `${pct}%`,
                    background: pct >= 90 ? '#0d9488' : pct >= 70 ? '#f59e0b' : '#ef4444',
                  }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Resource group table ───────────────────────────────────────────────────
function RgTable({ groups, loading }) {
  if (loading) return <Skeleton className="h-48 rounded-xl" />;
  if (!groups?.length) return null;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden shadow-sm">
      <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700">
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Compliance by resource group</h3>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">Sorted worst-first — focus remediation effort on the top rows</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 dark:border-gray-700 text-left">
              {['Resource group', 'Total resources', 'Compliant', 'Score'].map((h) => (
                <th key={h} className="px-4 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.map((g, i) => {
              const c = scoreColour(g.score_pct);
              return (
                <tr key={i} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors">
                  <td className="px-4 py-2.5 font-medium text-gray-800 dark:text-gray-100 font-mono text-xs">{g.resource_group}</td>
                  <td className="px-4 py-2.5 tabular-nums text-gray-600 dark:text-gray-300">{g.total}</td>
                  <td className="px-4 py-2.5 tabular-nums text-gray-600 dark:text-gray-300">{g.compliant}</td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <div className="w-20 bg-gray-100 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
                        <div className="h-1.5 rounded-full" style={{ width: `${g.score_pct}%`, background: g.score_pct >= 90 ? '#0d9488' : g.score_pct >= 70 ? '#f59e0b' : '#ef4444' }} />
                      </div>
                      <span className={`text-xs font-semibold tabular-nums ${c.text}`}>{g.score_pct}%</span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Non-compliant resources table ──────────────────────────────────────────
const NC_COLS = [
  { key: 'resource_name', label: 'Resource' },
  { key: 'resource_type', label: 'Type' },
  { key: 'resource_group', label: 'Resource group' },
  { key: 'compliance_pct', label: 'Tag coverage' },
  { key: 'missing_tags', label: 'Missing tags' },
];

function NonCompliantTable({ resources, loading }) {
  const [sortKey, setSortKey] = useState('compliance_pct');
  const [sortDir, setSortDir] = useState('asc');
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 25;

  const filtered = useMemo(() => {
    if (!resources?.length) return [];
    const q = filter.toLowerCase();
    return resources.filter((r) =>
      !q || r.resource_name?.toLowerCase().includes(q) || r.resource_group?.toLowerCase().includes(q) || r.resource_type?.toLowerCase().includes(q)
    );
  }, [resources, filter]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const av = a[sortKey] ?? 0;
      const bv = b[sortKey] ?? 0;
      if (typeof av === 'number') return sortDir === 'asc' ? av - bv : bv - av;
      return sortDir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
  }, [filtered, sortKey, sortDir]);

  const page_items = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.ceil(sorted.length / PAGE_SIZE);

  function toggleSort(key) {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('asc'); }
    setPage(0);
  }

  if (loading) return <Skeleton className="h-64 rounded-xl" />;
  if (!resources?.length) return null;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden shadow-sm">
      <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Non-compliant resources</h3>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{resources.length} resources missing ≥1 required tag</p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text" value={filter} onChange={(e) => { setFilter(e.target.value); setPage(0); }}
            placeholder="Filter by name, group, or type…"
            className="rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 px-3 py-1.5 text-xs text-gray-800 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 w-60"
          />
          {totalPages > 1 && (
            <div className="flex items-center gap-1.5 text-xs text-gray-500">
              <button disabled={page === 0} onClick={() => setPage((p) => p - 1)} className="disabled:opacity-40 hover:text-teal-600">←</button>
              <span>{page + 1}/{totalPages}</span>
              <button disabled={page >= totalPages - 1} onClick={() => setPage((p) => p + 1)} className="disabled:opacity-40 hover:text-teal-600">→</button>
            </div>
          )}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 dark:border-gray-700 text-left">
              {NC_COLS.map((c) => (
                <th key={c.key} className="px-4 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400 cursor-pointer select-none hover:text-teal-600 whitespace-nowrap" onClick={() => toggleSort(c.key)}>
                  <span className="flex items-center gap-1">{c.label}{sortKey === c.key && (sortDir === 'asc' ? <ChevronUp size={11} /> : <ChevronDown size={11} />)}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {page_items.map((r, i) => (
              <tr key={i} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors">
                <td className="px-4 py-2.5 font-medium text-gray-800 dark:text-gray-100 max-w-[160px] truncate" title={r.resource_name}>{r.resource_name || '—'}</td>
                <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400 text-xs font-mono max-w-[180px] truncate" title={r.resource_type}>{r.resource_type}</td>
                <td className="px-4 py-2.5 text-gray-600 dark:text-gray-300 text-xs font-mono">{r.resource_group}</td>
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <div className="w-16 bg-gray-100 dark:bg-gray-700 rounded-full h-1.5 overflow-hidden">
                      <div className="h-1.5 rounded-full" style={{ width: `${r.compliance_pct}%`, background: r.compliance_pct >= 70 ? '#f59e0b' : '#ef4444' }} />
                    </div>
                    <span className="text-xs tabular-nums text-gray-600 dark:text-gray-300">{r.compliance_pct}%</span>
                  </div>
                </td>
                <td className="px-4 py-2.5">
                  <div className="flex flex-wrap gap-1">
                    {r.missing_tags.map((t) => (
                      <span key={t} className="rounded-full bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-300 px-1.5 py-0.5 text-xs font-mono">
                        {t}
                      </span>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Required tags editor ───────────────────────────────────────────────────
function TagEditor({ tags, setTags }) {
  const [newTag, setNewTag] = useState('');
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {tags.map((t) => (
        <span key={t} className="flex items-center gap-1 rounded-full border border-gray-200 dark:border-gray-600 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 text-xs font-mono text-gray-700 dark:text-gray-200">
          {t}
          <button onClick={() => setTags((ts) => ts.filter((x) => x !== t))} className="text-gray-400 hover:text-red-500"><X size={10} /></button>
        </span>
      ))}
      <form onSubmit={(e) => { e.preventDefault(); const v = newTag.trim().toLowerCase(); if (v && !tags.includes(v)) setTags((ts) => [...ts, v]); setNewTag(''); }} className="flex items-center gap-1">
        <input
          type="text" value={newTag} onChange={(e) => setNewTag(e.target.value)}
          placeholder="add tag…"
          className="rounded-lg border border-dashed border-gray-300 dark:border-gray-600 bg-transparent px-2 py-0.5 text-xs text-gray-600 dark:text-gray-300 placeholder-gray-400 focus:outline-none focus:border-teal-500 w-24"
        />
        <button type="submit" className="text-teal-600 hover:text-teal-700"><Plus size={14} /></button>
      </form>
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────────────────
export default function TagCompliancePage() {
  const ctxSub = useCtxSub();
  const [subId, setSubId] = useState(ctxSub ?? '');
  const [requiredTags, setRequiredTags] = useState(DEFAULT_TAGS);
  const [score, setScore] = useState(null);
  const [groups, setGroups] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!subId.trim()) return;
    setLoading(true); setError(null);
    try {
      const [sc, gr] = await Promise.all([
        fetchComplianceScore(subId, { required_tags: requiredTags }),
        fetchComplianceGroups(subId, requiredTags),
      ]);
      setScore(sc); setGroups(gr);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [subId, requiredTags]);

  const colours = scoreColour(score?.score_pct);
  const totalResources = score?.total_resources ?? '—';
  const compliantCount = score?.fully_compliant ?? '—';
  const nonCompliantCount = score?.non_compliant_count ?? '—';

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 px-4 py-6 md:px-8">
      {/* Header */}
      <div className="mb-5">
        <div className="flex items-center gap-2 mb-1">
          <Tag size={20} className="text-teal-600" />
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-50">Tag Compliance Scorecard</h1>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Measure tagging coverage across your Azure subscription — spot untagged resources and focus remediation effort.
        </p>
      </div>

      {/* Controls */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm px-4 py-3 mb-5">
        <div className="flex flex-wrap items-start gap-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Subscription ID</label>
            <input
              type="text" value={subId} onChange={(e) => setSubId(e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              className="rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 px-3 py-1.5 text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 w-72"
            />
          </div>
          <div className="flex-1">
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Required tags</label>
            <TagEditor tags={requiredTags} setTags={setRequiredTags} />
          </div>
          <div className="self-end">
            <button
              onClick={load} disabled={loading}
              className="flex items-center gap-1.5 rounded-lg bg-teal-600 hover:bg-teal-700 disabled:opacity-50 px-4 py-1.5 text-sm font-medium text-white transition-colors"
            >
              <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              {loading ? 'Scoring…' : 'Score'}
            </button>
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />{error}
        </div>
      )}

      {/* Score gauge + KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-5">
        {/* Gauge */}
        <div className="md:col-span-1 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm flex flex-col items-center justify-center py-4">
          <ScoreGauge pct={score?.score_pct ?? null} loading={loading} />
          {!loading && score?.score_pct != null && (
            <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold -mt-2 ${colours.badge}`}>
              {score.score_pct >= 90 ? 'Excellent' : score.score_pct >= 70 ? 'Needs work' : 'Poor'}
            </span>
          )}
        </div>
        {/* KPI cards */}
        <div className="md:col-span-3 grid grid-cols-3 gap-3">
          {loading ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-20 rounded-xl" />) : (
            <>
              <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm flex items-start gap-3 px-4 py-3">
                <Tag size={16} className="mt-1 text-teal-500" />
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Total resources</p>
                  <p className="text-2xl font-bold tabular-nums text-gray-900 dark:text-gray-50">{totalResources}</p>
                </div>
              </div>
              <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm flex items-start gap-3 px-4 py-3">
                <CheckCircle size={16} className="mt-1 text-teal-500" />
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Fully compliant</p>
                  <p className="text-2xl font-bold tabular-nums text-teal-600 dark:text-teal-400">{compliantCount}</p>
                </div>
              </div>
              <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm flex items-start gap-3 px-4 py-3">
                <XCircle size={16} className="mt-1 text-red-500" />
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Non-compliant</p>
                  <p className="text-2xl font-bold tabular-nums text-red-600 dark:text-red-400">{nonCompliantCount}</p>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Per-tag coverage */}
      <div className="mb-5">
        <TagCoverageBars tagCoverage={score?.tag_coverage_pct} loading={loading} />
      </div>

      {/* Resource group table */}
      <div className="mb-5">
        <RgTable groups={groups?.groups} loading={loading} />
      </div>

      {/* Non-compliant resources */}
      <NonCompliantTable resources={score?.non_compliant_resources} loading={loading} />
    </div>
  );
}
