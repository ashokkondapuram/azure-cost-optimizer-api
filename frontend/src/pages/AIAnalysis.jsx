/**
 * AI Analysis — Actionable Output page
 *
 * Surfaces the combined engine analysis in a prioritised, actionable format:
 *
 *  ┌─ KPI summary bar ───────────────────────────────────────────┐
 *  ├─ High-priority actions (cross-ref: advisor + finding on same resource) ┤
 *  ├─ Advisor recommendations by category (collapsible) ─────────────┤
 *  ├─ Advanced scoring scoreboard (sortable, filterable, paginated) ───┤
 *  └─ Resource findings severity breakdown ─────────────────────┘
 *
 * Data: GET /engine/analysis/{id}/combined
 *       POST /engine/analysis/{id}/run  ("Run Engine" button)
 */

import React, { useState, useMemo, useCallback, useContext } from 'react';
import {
  Zap, DollarSign, AlertTriangle, ChevronDown, ChevronUp,
  RefreshCw, Play, CheckCircle, Star, Info, TrendingDown,
} from 'lucide-react';
import { fetchCombinedAnalysis, runEngineAnalysis } from '../api/engineAnalysis';

let SubscriptionContext;
try { ({ SubscriptionContext } = require('../context/SubscriptionContext')); } catch { SubscriptionContext = null; }
function useCtxSub() {
  const ctx = SubscriptionContext ? useContext(SubscriptionContext) : null; // eslint-disable-line
  return ctx?.subscriptionId ?? ctx?.activeSubscription ?? null;
}

// ── helpers ────────────────────────────────────────────────────────────────
const fmt = (n, cur = 'CAD') =>
  n != null
    ? new Intl.NumberFormat('en-CA', { style: 'currency', currency: cur, maximumFractionDigits: 0 }).format(n)
    : '—';

const IMPACT_BADGE = {
  high:   'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  medium: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  low:    'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
};

const TIER_BADGE = {
  critical: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  high:     'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
  medium:   'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  low:      'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300',
};

const CATEGORY_COLOUR = {
  cost:        'border-teal-400 bg-teal-50 dark:bg-teal-900/10',
  performance: 'border-blue-400 bg-blue-50 dark:bg-blue-900/10',
  security:    'border-red-400 bg-red-50 dark:bg-red-900/10',
  reliability: 'border-amber-400 bg-amber-50 dark:bg-amber-900/10',
  default:     'border-gray-300 bg-gray-50 dark:bg-gray-800',
};

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3, info: 4, unknown: 5 };

function Skeleton({ className = '' }) {
  return <div className={`animate-pulse rounded bg-gray-200 dark:bg-gray-700 ${className}`} />;
}

function KpiCard({ label, value, sub, icon: Icon, accent }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-3 shadow-sm">
      <div className={`mt-0.5 rounded-lg p-2 ${accent}`}><Icon size={16} /></div>
      <div>
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400">{label}</p>
        <p className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">{value}</p>
        {sub && <p className="text-xs text-gray-400 dark:text-gray-500">{sub}</p>}
      </div>
    </div>
  );
}

// ── High-priority action cards ──────────────────────────────────────────────
function HighPriorityActions({ items, loading, currency }) {
  const hp = useMemo(() => (items ?? []).filter((i) => i.high_priority).slice(0, 10), [items]);
  if (loading) return <Skeleton className="h-48 rounded-xl" />;
  if (!hp.length) return null;

  return (
    <div className="rounded-xl border border-orange-200 dark:border-orange-800 bg-orange-50 dark:bg-orange-900/10 shadow-sm overflow-hidden mb-5">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-orange-200 dark:border-orange-800">
        <Star size={15} className="text-orange-500" />
        <h2 className="text-sm font-semibold text-orange-800 dark:text-orange-200">High-priority actions</h2>
        <span className="ml-1 rounded-full bg-orange-200 dark:bg-orange-800 text-orange-800 dark:text-orange-200 px-2 py-0.5 text-xs font-medium">
          {hp.length}
        </span>
        <p className="ml-2 text-xs text-orange-600 dark:text-orange-400">
          Resources flagged by both Azure Advisor and resource findings
        </p>
      </div>
      <div className="divide-y divide-orange-100 dark:divide-orange-900/30">
        {hp.map((item, i) => (
          <div key={i} className="flex items-start justify-between gap-4 px-4 py-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-sm text-gray-900 dark:text-gray-50 truncate max-w-xs">
                  {item.resource_name || item.resource_id || 'Unknown resource'}
                </span>
                {item.tier && (
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${TIER_BADGE[item.tier?.toLowerCase()] ?? TIER_BADGE.medium}`}>
                    {item.tier}
                  </span>
                )}
                <span className="rounded-full bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300 px-2 py-0.5 text-xs font-medium">
                  ★ Both advisor + finding
                </span>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 font-mono truncate">
                {item.resource_type} {item.resource_group ? `· ${item.resource_group}` : ''}
              </p>
            </div>
            <div className="text-right shrink-0">
              {item.composite_score != null && (
                <p className="text-sm font-bold tabular-nums text-gray-800 dark:text-gray-100">
                  Score {item.composite_score}
                </p>
              )}
              {item.estimated_savings_usd != null && (
                <p className="text-xs tabular-nums text-teal-600 dark:text-teal-400">
                  {fmt(item.estimated_savings_usd)}/mo
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Advisor categories (collapsible accordion) ─────────────────────────────
function AdvisorCategoryPanel({ category, data, currency }) {
  const [open, setOpen] = useState(category === 'cost');
  const colour = CATEGORY_COLOUR[category] ?? CATEGORY_COLOUR.default;

  return (
    <div className={`rounded-xl border-l-4 ${colour} overflow-hidden`}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold capitalize text-gray-800 dark:text-gray-100">{category}</span>
          <span className="rounded-full bg-white/60 dark:bg-gray-800/60 border border-gray-200 dark:border-gray-700 px-2 py-0.5 text-xs font-medium tabular-nums text-gray-600 dark:text-gray-300">
            {data.count} recommendations
          </span>
          {data.count > 0 && category === 'cost' && (
            <span className="text-xs tabular-nums text-teal-600 dark:text-teal-400 font-medium">
              {fmt(data.items.reduce((s, i) => s + (i.potential_savings_monthly ?? 0), 0), currency)}/mo savings
            </span>
          )}
        </div>
        {open ? <ChevronUp size={15} className="text-gray-400" /> : <ChevronDown size={15} className="text-gray-400" />}
      </button>
      {open && data.items?.length > 0 && (
        <div className="border-t border-gray-100 dark:border-gray-700 divide-y divide-gray-50 dark:divide-gray-800">
          {data.items.slice(0, 20).map((rec, i) => (
            <div key={i} className="flex items-start justify-between gap-4 px-4 py-2.5">
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${IMPACT_BADGE[(rec.impact || 'low').toLowerCase()] ?? IMPACT_BADGE.low}`}>
                    {rec.impact}
                  </span>
                  <span className="text-sm text-gray-800 dark:text-gray-100">{rec.short_description}</span>
                </div>
                <p className="text-xs text-gray-400 dark:text-gray-500 font-mono mt-0.5 truncate" title={rec.resource_id}>
                  {rec.resource_id}
                </p>
              </div>
              {rec.potential_savings_monthly > 0 && (
                <span className="text-xs tabular-nums font-semibold text-teal-600 dark:text-teal-400 shrink-0">
                  {fmt(rec.potential_savings_monthly, currency)}/mo
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AdvisorSection({ advisor, loading, currency }) {
  if (loading) return <Skeleton className="h-40 rounded-xl" />;
  if (!advisor?.by_category || Object.keys(advisor.by_category).length === 0) return null;
  const cats = Object.entries(advisor.by_category).sort((a, b) => b[1].count - a[1].count);
  return (
    <div className="mb-5">
      <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-2">
        Azure Advisor recommendations
        <span className="ml-2 text-gray-400 font-normal text-xs">{advisor.total} active</span>
      </h2>
      <div className="space-y-2">
        {cats.map(([cat, data]) => (
          <AdvisorCategoryPanel key={cat} category={cat} data={data} currency={currency} />
        ))}
      </div>
    </div>
  );
}

// ── Advanced scoring scoreboard ─────────────────────────────────────────────
const SCORE_COLS = [
  { key: 'composite_score', label: 'Score' },
  { key: 'resource_name',   label: 'Resource' },
  { key: 'resource_type',   label: 'Type' },
  { key: 'tier',            label: 'Tier' },
  { key: 'estimated_savings_usd', label: 'Est. savings' },
  { key: 'flags',           label: 'Flags' },
];

function ScoreboardTable({ items, loading, currency }) {
  const [sortKey, setSortKey] = useState('composite_score');
  const [sortDir, setSortDir] = useState('desc');
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(0);
  const PAGE = 25;

  const filtered = useMemo(() => {
    if (!items?.length) return [];
    const q = filter.toLowerCase();
    return items.filter((r) =>
      !q ||
      r.resource_name?.toLowerCase().includes(q) ||
      r.resource_type?.toLowerCase().includes(q) ||
      r.tier?.toLowerCase().includes(q)
    );
  }, [items, filter]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const av = a[sortKey] ?? 0, bv = b[sortKey] ?? 0;
      if (typeof av === 'number') return sortDir === 'asc' ? av - bv : bv - av;
      return sortDir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
  }, [filtered, sortKey, sortDir]);

  const pageItems = sorted.slice(page * PAGE, (page + 1) * PAGE);
  const totalPages = Math.ceil(sorted.length / PAGE);

  function toggleSort(key) {
    if (key === sortKey) setSortDir((d) => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('desc'); }
    setPage(0);
  }

  if (loading) return <Skeleton className="h-64 rounded-xl" />;
  if (!items?.length) return null;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden shadow-sm mb-5">
      <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Advanced scoring scoreboard</h2>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{items.length} resources — ranked by composite score</p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="text" value={filter} onChange={(e) => { setFilter(e.target.value); setPage(0); }}
            placeholder="Filter by name, type, or tier…"
            className="rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 px-3 py-1.5 text-xs placeholder-gray-400 text-gray-800 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-teal-500 w-56"
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
              {SCORE_COLS.map((c) => (
                <th
                  key={c.key}
                  onClick={() => c.key !== 'flags' && toggleSort(c.key)}
                  className={`px-4 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400 whitespace-nowrap ${
                    c.key !== 'flags' ? 'cursor-pointer select-none hover:text-teal-600' : ''
                  }`}
                >
                  <span className="flex items-center gap-1">
                    {c.label}
                    {sortKey === c.key && (sortDir === 'asc' ? <ChevronUp size={11}/> : <ChevronDown size={11}/>)}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageItems.map((item, i) => (
              <tr key={i} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors">
                <td className="px-4 py-2.5">
                  <span className="inline-flex items-center justify-center w-9 h-9 rounded-full bg-teal-50 dark:bg-teal-900/30 text-teal-700 dark:text-teal-300 font-bold tabular-nums text-sm">
                    {item.composite_score ?? '—'}
                  </span>
                </td>
                <td className="px-4 py-2.5 font-medium text-gray-800 dark:text-gray-100 max-w-[160px] truncate" title={item.resource_name}>
                  {item.resource_name || item.resource_id || '—'}
                </td>
                <td className="px-4 py-2.5 text-gray-500 dark:text-gray-400 text-xs font-mono max-w-[160px] truncate" title={item.resource_type}>
                  {item.resource_type}
                </td>
                <td className="px-4 py-2.5">
                  {item.tier && (
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${TIER_BADGE[item.tier?.toLowerCase()] ?? TIER_BADGE.medium}`}>
                      {item.tier}
                    </span>
                  )}
                </td>
                <td className="px-4 py-2.5 tabular-nums font-semibold text-teal-600 dark:text-teal-400 whitespace-nowrap">
                  {item.estimated_savings_usd != null ? `${fmt(item.estimated_savings_usd)}/mo` : '—'}
                </td>
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-1.5">
                    {item.high_priority && (
                      <span title="Both advisor & finding" className="text-orange-500"><Star size={13}/></span>
                    )}
                    {item.has_advisor_recommendation && (
                      <span title="Advisor recommendation" className="text-blue-500"><CheckCircle size={13}/></span>
                    )}
                    {item.has_open_finding && (
                      <span title="Open finding" className="text-red-400"><AlertTriangle size={13}/></span>
                    )}
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

// ── Severity breakdown bar ──────────────────────────────────────────────────
const SEV_COLOUR = {
  critical: '#ef4444', high: '#f97316', medium: '#f59e0b', low: '#6b7280', unknown: '#9ca3af',
};
function SeverityBreakdown({ findings, loading }) {
  if (loading) return <Skeleton className="h-20 rounded-xl" />;
  if (!findings?.by_severity || Object.keys(findings.by_severity).length === 0) return null;
  const entries = Object.entries(findings.by_severity).sort(
    (a, b) => (SEVERITY_ORDER[a[0]] ?? 9) - (SEVERITY_ORDER[b[0]] ?? 9)
  );
  const total = entries.reduce((s, [, v]) => s + v, 0);
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm p-4 mb-5">
      <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-3">
        Resource findings by severity
        <span className="ml-2 text-xs font-normal text-gray-400">{total} open / acknowledged</span>
      </h2>
      <div className="flex rounded-full overflow-hidden h-5 gap-px mb-3">
        {entries.map(([sev, count]) => (
          <div
            key={sev}
            style={{ width: `${(count / total) * 100}%`, background: SEV_COLOUR[sev] ?? SEV_COLOUR.unknown }}
            title={`${sev}: ${count}`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-4">
        {entries.map(([sev, count]) => (
          <div key={sev} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: SEV_COLOUR[sev] ?? '#9ca3af' }} />
            <span className="text-xs capitalize text-gray-600 dark:text-gray-300">{sev}</span>
            <span className="text-xs font-semibold tabular-nums text-gray-800 dark:text-gray-100">{count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Run engine status banner ─────────────────────────────────────────────────
function RunStatusBanner({ status, onClose }) {
  if (!status) return null;
  const ok = status.status === 'ok';
  const steps = Object.entries(status.steps ?? {});
  return (
    <div className={`mb-5 rounded-xl border px-4 py-3 text-sm ${
      ok ? 'border-teal-200 dark:border-teal-800 bg-teal-50 dark:bg-teal-900/20 text-teal-700 dark:text-teal-300'
         : 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300'
    }`}>
      <div className="flex items-center justify-between mb-2">
        <span className="font-semibold">{ok ? '✅ Engine run complete' : '⚠ Engine run had issues'}</span>
        <button onClick={onClose} className="text-xs opacity-60 hover:opacity-100">Dismiss</button>
      </div>
      {steps.map(([step, res]) => (
        <div key={step} className="text-xs opacity-80">
          <span className="font-mono">{step}</span>: {res.status ?? JSON.stringify(res)}
        </div>
      ))}
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────────────────
export default function AIAnalysis() {
  const ctxSub = useCtxSub();
  const [subId, setSubId] = useState(ctxSub ?? '');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [runStatus, setRunStatus] = useState(null);

  const load = useCallback(async () => {
    if (!subId.trim()) return;
    setLoading(true); setError(null);
    try {
      const d = await fetchCombinedAnalysis(subId, { top_n: 50 });
      setData(d);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [subId]);

  const runEngine = useCallback(async () => {
    if (!subId.trim()) return;
    setRunning(true); setRunStatus(null);
    try {
      const res = await runEngineAnalysis(subId);
      setRunStatus(res);
      // Reload data after engine run
      await load();
    } catch (e) {
      setRunStatus({ status: 'error', steps: { run: { status: e.message } } });
    } finally {
      setRunning(false);
    }
  }, [subId, load]);

  const currency = data?.advisor?.by_category?.cost?.items?.[0]?.currency ?? 'CAD';
  const scoreboard = data?.advanced_scoring?.items ?? [];
  const totalSavings = data?.combined_estimated_monthly_savings;
  const advisorTotal = data?.advisor?.total ?? '—';
  const findingsTotal = data?.resource_findings?.total ?? '—';
  const crossRef = data?.cross_reference?.resources_in_both_advisor_and_findings ?? '—';

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 px-4 py-6 md:px-8">
      {/* Header */}
      <div className="mb-5">
        <div className="flex items-center gap-2 mb-1">
          <Zap size={20} className="text-teal-600" />
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-50">AI Analysis</h1>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Combined Azure Advisor + resource findings + advanced scoring — cross-referenced into a single actionable view.
        </p>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <input
          type="text" value={subId} onChange={(e) => setSubId(e.target.value)}
          placeholder="Subscription ID"
          className="rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-1.5 text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 w-80"
        />
        <button
          onClick={load} disabled={loading}
          className="flex items-center gap-1.5 rounded-lg bg-teal-600 hover:bg-teal-700 disabled:opacity-50 px-4 py-1.5 text-sm font-medium text-white transition-colors"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Analysing…' : 'Analyse'}
        </button>
        <button
          onClick={runEngine} disabled={running || loading}
          className="flex items-center gap-1.5 rounded-lg border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 px-4 py-1.5 text-sm text-gray-700 dark:text-gray-300 transition-colors"
        >
          <Play size={14} className={running ? 'animate-pulse text-orange-500' : ''} />
          {running ? 'Running engine…' : 'Run engine'}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />{error}
        </div>
      )}

      {/* Run status banner */}
      <RunStatusBanner status={runStatus} onClose={() => setRunStatus(null)} />

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        {loading ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-xl" />) : (
          <>
            <KpiCard label="Est. monthly savings" value={fmt(totalSavings, currency)} sub="advisor + findings" icon={DollarSign} accent="bg-teal-100 text-teal-600 dark:bg-teal-900/40 dark:text-teal-400" />
            <KpiCard label="Advisor recommendations" value={advisorTotal} sub="active" icon={CheckCircle} accent="bg-blue-100 text-blue-600 dark:bg-blue-900/40 dark:text-blue-400" />
            <KpiCard label="Open findings" value={findingsTotal} sub="open / acknowledged" icon={AlertTriangle} accent="bg-amber-100 text-amber-600 dark:bg-amber-900/40 dark:text-amber-400" />
            <KpiCard label="High-priority resources" value={crossRef} sub="in both advisor + findings" icon={Star} accent="bg-orange-100 text-orange-600 dark:bg-orange-900/40 dark:text-orange-400" />
          </>
        )}
      </div>

      {/* High priority */}
      <HighPriorityActions items={scoreboard} loading={loading} currency={currency} />

      {/* Advisor section */}
      <AdvisorSection advisor={data?.advisor} loading={loading} currency={currency} />

      {/* Severity breakdown */}
      <SeverityBreakdown findings={data?.resource_findings} loading={loading} />

      {/* Scoreboard */}
      <ScoreboardTable items={scoreboard} loading={loading} currency={currency} />

      {/* Empty state */}
      {!loading && !data && !error && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500 gap-3">
          <Zap size={40} strokeWidth={1.5} />
          <p className="text-sm font-medium">Enter a subscription ID and click Analyse</p>
          <p className="text-xs">Or click “Run engine” to trigger a full analysis pass first</p>
        </div>
      )}
    </div>
  );
}
