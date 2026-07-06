/**
 * Waste Heatmap page
 *
 * Visualises idle/orphaned resource waste as a CSS-grid heat map where
 * each cell is a resource category × severity combination, coloured by
 * estimated savings magnitude.  Below the heatmap a sortable findings
 * table lets engineers drill into individual items.
 *
 * Data source: GET /idle-resources/sweep/{subscriptionId}
 *              GET /idle-resources/summary/{subscriptionId}
 */

import React, { useState, useMemo, useCallback, useContext } from 'react';
import { RefreshCw, Flame, DollarSign, AlertTriangle, ChevronUp, ChevronDown, Info } from 'lucide-react';
import { fetchIdleSweep, fetchIdleSummary } from '../api/wasteHeatmap';

let SubscriptionContext;
try { ({ SubscriptionContext } = require('../context/SubscriptionContext')); } catch { SubscriptionContext = null; }
function useCtxSub() {
  const ctx = SubscriptionContext ? useContext(SubscriptionContext) : null; // eslint-disable-line
  return ctx?.subscriptionId ?? ctx?.activeSubscription ?? null;
}

// ── helpers ────────────────────────────────────────────────────────────────
const fmtUSD = (n) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n);

const SEVERITIES = ['critical', 'high', 'medium', 'low'];
const SEVERITY_LABEL = { critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low' };

// Heat intensity → Tailwind bg classes (warm palette: white → amber → red)
function heatClass(savings, maxSavings) {
  if (!savings || maxSavings === 0) return 'bg-gray-100 dark:bg-gray-800 text-gray-400';
  const ratio = savings / maxSavings;
  if (ratio >= 0.75) return 'bg-red-500 text-white';
  if (ratio >= 0.5)  return 'bg-orange-400 text-white';
  if (ratio >= 0.25) return 'bg-amber-300 text-gray-900';
  return 'bg-yellow-100 text-gray-700 dark:bg-yellow-900/40 dark:text-yellow-200';
}

const SEVERITY_BADGE = {
  critical: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  high:     'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
  medium:   'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  low:      'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
};

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

// ── Heatmap grid ───────────────────────────────────────────────────────────
function HeatmapGrid({ items, loading }) {
  const { categories, grid, maxSavings } = useMemo(() => {
    if (!items?.length) return { categories: [], grid: {}, maxSavings: 0 };
    const cats = [...new Set(items.map((i) => i.category))].sort();
    const g = {};
    let max = 0;
    for (const item of items) {
      const key = `${item.category}|${item.severity}`;
      if (!g[key]) g[key] = { count: 0, savings: 0 };
      g[key].count += 1;
      g[key].savings += item.estimated_savings_usd ?? 0;
      if (g[key].savings > max) max = g[key].savings;
    }
    return { categories: cats, grid: g, maxSavings: max };
  }, [items]);

  if (loading) return <Skeleton className="h-52 rounded-xl" />;
  if (!categories.length) return (
    <div className="flex items-center justify-center h-40 text-sm text-gray-400 dark:text-gray-500">
      No idle resource data — enter a subscription ID and click Scan
    </div>
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-separate border-spacing-1">
        <thead>
          <tr>
            <th className="text-left text-xs font-semibold text-gray-500 dark:text-gray-400 pb-1 pr-2 whitespace-nowrap">Category</th>
            {SEVERITIES.map((s) => (
              <th key={s} className="text-center text-xs font-semibold text-gray-500 dark:text-gray-400 pb-1 px-1">
                {SEVERITY_LABEL[s]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {categories.map((cat) => (
            <tr key={cat}>
              <td className="text-xs font-medium text-gray-700 dark:text-gray-300 pr-3 py-0.5 whitespace-nowrap">{cat}</td>
              {SEVERITIES.map((sev) => {
                const cell = grid[`${cat}|${sev}`];
                const cls = heatClass(cell?.savings ?? 0, maxSavings);
                return (
                  <td key={sev} className="p-0.5">
                    <div
                      title={cell ? `${cell.count} finding${cell.count !== 1 ? 's' : ''} · ${fmtUSD(cell.savings)}` : 'No findings'}
                      className={`rounded-lg w-full min-w-[72px] py-2 px-1 text-center transition-opacity hover:opacity-90 cursor-default ${cls}`}
                    >
                      {cell ? (
                        <>
                          <div className="font-bold tabular-nums text-sm leading-tight">{cell.count}</div>
                          <div className="text-xs opacity-80 tabular-nums leading-tight">{fmtUSD(cell.savings)}</div>
                        </>
                      ) : (
                        <div className="text-xs opacity-40">—</div>
                      )}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
        Cell colour = estimated savings intensity. Darker = more waste. Hover for exact values.
      </p>
    </div>
  );
}

// ── Findings table ─────────────────────────────────────────────────────────
const COLS = [
  { key: 'resource_name', label: 'Resource' },
  { key: 'category', label: 'Category' },
  { key: 'severity', label: 'Severity' },
  { key: 'title', label: 'Finding' },
  { key: 'estimated_savings_usd', label: 'Est. savings' },
];

function FindingsTable({ items, loading }) {
  const [sortKey, setSortKey] = useState('estimated_savings_usd');
  const [sortDir, setSortDir] = useState('desc');
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 20;

  const sorted = useMemo(() => {
    if (!items?.length) return [];
    return [...items].sort((a, b) => {
      const av = a[sortKey] ?? '';
      const bv = b[sortKey] ?? '';
      if (typeof av === 'number') return sortDir === 'asc' ? av - bv : bv - av;
      return sortDir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
  }, [items, sortKey, sortDir]);

  const page_items = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.ceil(sorted.length / PAGE_SIZE);

  function toggleSort(key) {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('desc'); }
    setPage(0);
  }

  if (loading) return <Skeleton className="h-48 rounded-xl" />;
  if (!items?.length) return null;

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden shadow-sm">
      <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">All idle resource findings</h3>
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{sorted.length} findings — click column headers to sort</p>
        </div>
        {totalPages > 1 && (
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <button disabled={page === 0} onClick={() => setPage((p) => p - 1)} className="disabled:opacity-40 hover:text-teal-600">← Prev</button>
            <span>Page {page + 1} / {totalPages}</span>
            <button disabled={page >= totalPages - 1} onClick={() => setPage((p) => p + 1)} className="disabled:opacity-40 hover:text-teal-600">Next →</button>
          </div>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 dark:border-gray-700 text-left">
              {COLS.map((c) => (
                <th
                  key={c.key}
                  className="px-4 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400 cursor-pointer select-none hover:text-teal-600 whitespace-nowrap"
                  onClick={() => toggleSort(c.key)}
                >
                  <span className="flex items-center gap-1">
                    {c.label}
                    {sortKey === c.key && (sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {page_items.map((item, i) => (
              <tr key={item.finding_id ?? i} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors">
                <td className="px-4 py-2.5 font-medium text-gray-800 dark:text-gray-100 max-w-[180px] truncate" title={item.resource_name}>
                  {item.resource_name || item.resource_id || '—'}
                </td>
                <td className="px-4 py-2.5 text-gray-600 dark:text-gray-300 whitespace-nowrap">{item.category}</td>
                <td className="px-4 py-2.5">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${SEVERITY_BADGE[item.severity] ?? SEVERITY_BADGE.low}`}>
                    {item.severity}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-gray-600 dark:text-gray-300 max-w-[260px] truncate" title={item.title}>{item.title}</td>
                <td className="px-4 py-2.5 tabular-nums font-semibold text-gray-800 dark:text-gray-100 whitespace-nowrap">
                  {item.estimated_savings_usd ? fmtUSD(item.estimated_savings_usd) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Top rules bar chart (CSS-only) ─────────────────────────────────────────
function TopRulesChart({ rules, loading }) {
  if (loading) return <Skeleton className="h-40 rounded-xl" />;
  if (!rules?.length) return null;
  const top = rules.slice(0, 8);
  const max = top[0]?.savings_usd ?? 1;
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm p-4">
      <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-3">Top waste rules by savings potential</h3>
      <div className="space-y-2">
        {top.map((r) => (
          <div key={r.rule_id} className="flex items-center gap-3">
            <span className="text-xs text-gray-500 dark:text-gray-400 w-44 shrink-0 truncate" title={r.title ?? r.rule_id}>
              {r.title ?? r.rule_id}
            </span>
            <div className="flex-1 bg-gray-100 dark:bg-gray-700 rounded-full h-4 overflow-hidden">
              <div
                className="h-4 rounded-full bg-orange-400 transition-all"
                style={{ width: `${(r.savings_usd / max) * 100}%` }}
              />
            </div>
            <span className="text-xs tabular-nums font-semibold text-gray-700 dark:text-gray-200 w-20 text-right shrink-0">
              {fmtUSD(r.savings_usd)}
            </span>
            <span className="text-xs text-gray-400 dark:text-gray-500 w-12 text-right shrink-0">
              ×{r.count}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────────────────
export default function WasteHeatmap() {
  const ctxSub = useCtxSub();
  const [subId, setSubId] = useState(ctxSub ?? '');
  const [sweep, setSweep] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!subId.trim()) return;
    setLoading(true); setError(null);
    try {
      const [sw, sm] = await Promise.all([fetchIdleSweep(subId), fetchIdleSummary(subId)]);
      setSweep(sw); setSummary(sm);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [subId]);

  const items = sweep?.idle_resources ?? [];

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 px-4 py-6 md:px-8">
      {/* Header */}
      <div className="mb-5">
        <div className="flex items-center gap-2 mb-1">
          <Flame size={20} className="text-orange-500" />
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-50">Waste Heatmap</h1>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Idle, orphaned, and stale resources visualised by category × severity — sorted by estimated savings potential.
        </p>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <input
          type="text" value={subId} onChange={(e) => setSubId(e.target.value)}
          placeholder="Subscription ID"
          className="rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-1.5 text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-orange-400 w-80"
        />
        <button
          onClick={load} disabled={loading}
          className="flex items-center gap-1.5 rounded-lg bg-orange-500 hover:bg-orange-600 disabled:opacity-50 px-4 py-1.5 text-sm font-medium text-white transition-colors"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Scanning…' : 'Scan'}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />{error}
        </div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        {loading ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-xl" />) : (
          <>
            <KpiCard label="Total findings" value={sweep?.total_idle_findings ?? '—'} sub="open/active" icon={Flame} accent="bg-orange-100 text-orange-600 dark:bg-orange-900/40 dark:text-orange-400" />
            <KpiCard label="Est. savings" value={sweep ? fmtUSD(sweep.total_estimated_savings_usd) : '—'} sub="if all resolved" icon={DollarSign} accent="bg-green-100 text-green-600 dark:bg-green-900/40 dark:text-green-400" />
            <KpiCard label="Critical" value={sweep?.by_severity?.critical ?? '—'} sub="findings" icon={AlertTriangle} accent="bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400" />
            <KpiCard label="High" value={sweep?.by_severity?.high ?? '—'} sub="findings" icon={Info} accent="bg-amber-100 text-amber-600 dark:bg-amber-900/40 dark:text-amber-400" />
          </>
        )}
      </div>

      {/* Heatmap */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm p-4 mb-5">
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-1">Category × Severity heatmap</h2>
        <p className="text-xs text-gray-400 dark:text-gray-500 mb-4">Each cell shows finding count and estimated savings. Colour intensity = savings magnitude.</p>
        <HeatmapGrid items={items} loading={loading} />
      </div>

      {/* Top rules */}
      {(summary?.top_rules?.length > 0 || loading) && (
        <div className="mb-5">
          <TopRulesChart rules={summary?.top_rules} loading={loading} />
        </div>
      )}

      {/* Findings table */}
      <FindingsTable items={items} loading={loading} />
    </div>
  );
}
