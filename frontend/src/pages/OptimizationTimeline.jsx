/**
 * Optimization Timeline page
 *
 * Shows month-over-month cost trends to visualise whether optimisation
 * actions are translating into real spend reductions.
 *
 *  ┌─ KPI summary (net delta, best/worst month) ────────────────┐
 *  ├─ Timeline bar chart (monthly totals, green = savings, red = over) ┤
 *  ├─ Month comparisons (delta cards with trend arrows) ─────────┤
 *  └─ Service breakdown (select any two months to compare) ──────┘
 *
 * Data: GET /savings/month-over-month/{id}
 *       GET /savings/service-breakdown/{id}?base_month=&compare_month=
 */

import React, { useState, useMemo, useCallback, useEffect } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  Cell, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import {
  TrendingDown, TrendingUp, Minus,
  ArrowDown, ArrowUp,
} from 'lucide-react';
import { fetchMonthOverMonth, fetchServiceBreakdown } from '../api/optimizationTimeline';
import AdvancedToolLayout, { useAdvancedSubscription } from '../components/advanced/AdvancedToolLayout';

// ── helpers ────────────────────────────────────────────────────────────────
const fmt = (n, cur = 'CAD') =>
  n != null
    ? new Intl.NumberFormat('en-CA', { style: 'currency', currency: cur, maximumFractionDigits: 0 }).format(n)
    : '—';

const fmtMonth = (ym) => {
  try {
    const [y, m] = ym.split('-');
    return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString('en-CA', { month: 'short', year: '2-digit' });
  } catch { return ym; }
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

// ── Timeline bar chart ──────────────────────────────────────────────────────
function CustomBarTooltip({ active, payload, label, currency }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 shadow-lg text-sm">
      <p className="font-semibold text-gray-700 dark:text-gray-200">{fmtMonth(label)}</p>
      <p className="tabular-nums text-gray-600 dark:text-gray-300">{fmt(payload[0]?.value, currency)}</p>
    </div>
  );
}

function TimelineChart({ timeline, loading, currency, onSelectMonth }) {
  const [selected, setSelected] = useState(null);
  const firstSpend = timeline?.[0]?.total_spend ?? 0;

  if (loading) return <Skeleton className="h-64 rounded-xl" />;
  if (!timeline?.length) return (
    <div className="h-48 flex items-center justify-center text-sm text-gray-400 dark:text-gray-500">
      No data — enter a subscription ID and click Load
    </div>
  );

  return (
    <div>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={timeline} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
          onClick={(d) => {
            if (d?.activePayload?.[0]) {
              const m = d.activePayload[0].payload.month;
              setSelected(m);
              onSelectMonth && onSelectMonth(m);
            }
          }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(156,163,175,0.2)" />
          <ReferenceLine y={firstSpend} stroke="rgba(156,163,175,0.5)" strokeDasharray="4 4" label={{ value: 'baseline', fontSize: 10, fill: '#9ca3af', position: 'insideTopRight' }} />
          <XAxis dataKey="month" tickFormatter={fmtMonth} tick={{ fontSize: 11 }} stroke="rgba(156,163,175,0.4)" />
          <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11 }} stroke="rgba(156,163,175,0.4)" width={52} />
          <Tooltip content={<CustomBarTooltip currency={currency} />} />
          <Bar dataKey="total_spend" radius={[4, 4, 0, 0]}>
            {timeline.map((entry, i) => (
              <Cell
                key={entry.month}
                fill={
                  i === 0 ? '#6b7280'
                  : entry.total_spend < timeline[i - 1]?.total_spend ? '#0d9488'
                  : entry.total_spend > timeline[i - 1]?.total_spend ? '#ef4444'
                  : '#6b7280'
                }
                opacity={selected === entry.month ? 1 : 0.82}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="flex items-center gap-4 mt-2 text-xs text-gray-500 dark:text-gray-400">
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-teal-500" /> Savings vs prior month</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-red-400" /> Overspend vs prior month</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-sm bg-gray-400" /> Baseline / flat</span>
      </div>
    </div>
  );
}

// ── Comparison delta cards ───────────────────────────────────────────────────
function ComparisonCards({ comparisons, loading, currency, onSelectPair }) {
  if (loading) return <div className="flex gap-3">{Array.from({length:3}).map((_,i)=><Skeleton key={i} className="h-24 rounded-xl flex-1" />)}</div>;
  if (!comparisons?.length) return null;

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
      {comparisons.map((c) => {
        const isSavings = c.status === 'savings';
        const isFlat = c.status === 'flat';
        return (
          <button
            key={c.from_month}
            onClick={() => onSelectPair && onSelectPair(c.from_month, c.to_month)}
            className={`text-left rounded-xl border p-3 shadow-sm transition-colors hover:ring-2 ${
              isSavings
                ? 'border-teal-200 dark:border-teal-800 bg-teal-50 dark:bg-teal-900/10 hover:ring-teal-400'
                : isFlat
                ? 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:ring-gray-300'
                : 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/10 hover:ring-red-300'
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                {fmtMonth(c.from_month)} → {fmtMonth(c.to_month)}
              </span>
              {isSavings ? <TrendingDown size={14} className="text-teal-500" />
               : isFlat   ? <Minus size={14} className="text-gray-400" />
               : <TrendingUp size={14} className="text-red-500" />}
            </div>
            <p className={`text-lg font-bold tabular-nums ${
              isSavings ? 'text-teal-600 dark:text-teal-400' : isFlat ? 'text-gray-500' : 'text-red-600 dark:text-red-400'
            }`}>
              {isSavings ? '' : isFlat ? '' : '+'}{fmt(c.delta, c.currency)}
            </p>
            <p className={`text-xs tabular-nums font-medium ${
              isSavings ? 'text-teal-500' : isFlat ? 'text-gray-400' : 'text-red-400'
            }`}>
              {c.delta_pct > 0 ? '+' : ''}{c.delta_pct}%
            </p>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">Click to compare services</p>
          </button>
        );
      })}
    </div>
  );
}

// ── Service breakdown table ─────────────────────────────────────────────────
function ServiceBreakdown({ subId, baseMonth, compareMonth, currency }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    if (!subId || !baseMonth || !compareMonth) return;
    setLoading(true); setError(null);
    fetchServiceBreakdown(subId, baseMonth, compareMonth)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [subId, baseMonth, compareMonth]);

  if (!baseMonth || !compareMonth) return null;
  if (loading) return <Skeleton className="h-48 rounded-xl" />;
  if (error) return <div className="text-xs text-red-500 px-2">{error}</div>;
  if (!data?.services?.length) return null;

  const items = showAll ? data.services : data.services.slice(0, 15);
  const maxAbs = Math.max(...data.services.map((s) => Math.abs(s.delta)));

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700">
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">
          Service breakdown — {fmtMonth(baseMonth)} vs {fmtMonth(compareMonth)}
        </h3>
        <div className="flex gap-4 mt-1 text-xs">
          <span className="flex items-center gap-1 text-teal-600"><ArrowDown size={11}/>Savings: {fmt(data.total_savings, currency)}</span>
          <span className="flex items-center gap-1 text-red-500"><ArrowUp size={11}/>Overspend: {fmt(data.total_overspend, currency)}</span>
        </div>
      </div>
      <div className="divide-y divide-gray-50 dark:divide-gray-800">
        {items.map((svc) => {
          const isSavings = svc.status === 'savings';
          const barPct = maxAbs > 0 ? (Math.abs(svc.delta) / maxAbs) * 100 : 0;
          return (
            <div key={svc.service_name} className="flex items-center gap-3 px-4 py-2">
              <span className="text-xs text-gray-700 dark:text-gray-300 w-48 shrink-0 truncate" title={svc.service_name}>{svc.service_name}</span>
              <div className="flex-1 bg-gray-100 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
                <div
                  className={`h-2 rounded-full ${isSavings ? 'bg-teal-500' : 'bg-red-400'}`}
                  style={{ width: `${barPct}%` }}
                />
              </div>
              <span className={`text-xs tabular-nums font-semibold w-20 text-right shrink-0 ${
                isSavings ? 'text-teal-600 dark:text-teal-400' : 'text-red-500'
              }`}>
                {svc.delta > 0 ? '+' : ''}{fmt(svc.delta, currency)}
              </span>
              {svc.delta_pct != null && (
                <span className={`text-xs tabular-nums w-12 text-right shrink-0 ${
                  isSavings ? 'text-teal-500' : 'text-red-400'
                }`}>
                  {svc.delta_pct > 0 ? '+' : ''}{svc.delta_pct}%
                </span>
              )}
            </div>
          );
        })}
      </div>
      {data.services.length > 15 && (
        <div className="px-4 py-2 border-t border-gray-50 dark:border-gray-800">
          <button onClick={() => setShowAll((s) => !s)} className="text-xs text-teal-600 hover:underline">
            {showAll ? 'Show fewer' : `Show all ${data.services.length} services`}
          </button>
        </div>
      )}
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────────────────
export default function OptimizationTimeline() {
  const { subscription } = useAdvancedSubscription();
  const [monthsBack, setMonthsBack] = useState(6);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedPair, setSelectedPair] = useState({ base: null, compare: null });

  const load = useCallback(async () => {
    if (!subscription?.trim()) return;
    setLoading(true); setError(null);
    try {
      const d = await fetchMonthOverMonth(subscription, monthsBack);
      setData(d);
      // Auto-select the last two months for service breakdown
      const c = d.comparisons ?? [];
      if (c.length >= 1) setSelectedPair({ base: c[c.length - 1].from_month, compare: c[c.length - 1].to_month });
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [subscription, monthsBack]);

  useEffect(() => {
    load();
  }, [load]);

  const currency = data?.billing_currency ?? 'CAD';
  const netDelta = data?.net_delta_vs_oldest;
  const netStatus = data?.net_status;
  const bestMonth = useMemo(() => {
    if (!data?.comparisons?.length) return null;
    return data.comparisons.reduce((best, c) => (!best || c.delta < best.delta ? c : best), null);
  }, [data]);
  const worstMonth = useMemo(() => {
    if (!data?.comparisons?.length) return null;
    return data.comparisons.reduce((worst, c) => (!worst || c.delta > worst.delta ? c : worst), null);
  }, [data]);

  return (
    <AdvancedToolLayout
      title="Optimization timeline"
      subtitle="Month-over-month spend trends — see whether cost optimisation actions are translating into real savings."
      iconKey="optimizationTimeline"
      iconRoute="/timeline"
      onRefresh={load}
      loading={loading}
      error={error}
      errorTitle="Could not load optimization timeline"
    >
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-600 dark:text-gray-400">Months:</label>
          {[3, 6, 9, 12].map((n) => (
            <button
              key={n}
              onClick={() => setMonthsBack(n)}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                monthsBack === n
                  ? 'bg-teal-600 text-white'
                  : 'border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              {n}m
            </button>
          ))}
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-5">
        {loading ? Array.from({length:3}).map((_,i) => <Skeleton key={i} className="h-16 rounded-xl" />) : (
          <>
            <KpiCard
              label={`Net ${netStatus === 'savings' ? 'savings' : 'change'} (${monthsBack}m)`}
              value={netDelta != null ? fmt(Math.abs(netDelta), currency) : '—'}
              sub={netStatus === 'savings' ? 'vs oldest month' : netStatus === 'overspend' ? 'overspend vs oldest' : 'flat'}
              icon={netStatus === 'savings' ? TrendingDown : netStatus === 'overspend' ? TrendingUp : Minus}
              accent={netStatus === 'savings' ? 'bg-teal-100 text-teal-600 dark:bg-teal-900/40 dark:text-teal-400' : netStatus === 'overspend' ? 'bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400' : 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'}
            />
            <KpiCard
              label="Best month"
              value={bestMonth ? `${fmtMonth(bestMonth.to_month)}` : '—'}
              sub={bestMonth ? `${fmt(Math.abs(bestMonth.delta), currency)} saved` : 'no data'}
              icon={ArrowDown}
              accent="bg-teal-100 text-teal-600 dark:bg-teal-900/40 dark:text-teal-400"
            />
            <KpiCard
              label="Worst month"
              value={worstMonth?.delta > 0 ? `${fmtMonth(worstMonth.to_month)}` : '—'}
              sub={worstMonth?.delta > 0 ? `${fmt(worstMonth.delta, currency)} over` : 'all months improved'}
              icon={ArrowUp}
              accent="bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400"
            />
          </>
        )}
      </div>

      {/* Chart */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm p-4 mb-5">
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-1">Monthly spend — {monthsBack}m window</h2>
        <p className="text-xs text-gray-400 dark:text-gray-500 mb-4">Click a bar to drill into service-level changes for that month.</p>
        <TimelineChart
          timeline={data?.timeline}
          loading={loading}
          currency={currency}
          onSelectMonth={(m) => {
            const idx = (data?.timeline ?? []).findIndex((t) => t.month === m);
            if (idx > 0) setSelectedPair({ base: data.timeline[idx - 1].month, compare: m });
          }}
        />
      </div>

      {/* Comparison delta cards */}
      <div className="mb-5">
        <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100 mb-3">Month-over-month comparisons</h2>
        <ComparisonCards
          comparisons={data?.comparisons}
          loading={loading}
          currency={currency}
          onSelectPair={(base, compare) => setSelectedPair({ base, compare })}
        />
      </div>

      {/* Service breakdown */}
      {selectedPair.base && selectedPair.compare && (
        <ServiceBreakdown
          subId={subscription}
          baseMonth={selectedPair.base}
          compareMonth={selectedPair.compare}
          currency={currency}
        />
      )}
    </AdvancedToolLayout>
  );
}
