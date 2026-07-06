/**
 * Cost Anomaly Detector page
 *
 * Layout:
 *  ┌─ KPI bar ───────────────────────────────────────────┐
 *  ├─ Controls (subscription picker + parameter sliders) ─┤
 *  ├─ Time-series chart (daily cost + anomaly markers)  ──┤
 *  ├─ Anomaly alert list (severity-ranked, with actions) ─┤
 *  └─ Per-service anomaly table ───────────────────────────┘
 *
 * Real data is fetched from:
 *   GET /anomalies/daily/{subscriptionId}
 *   GET /anomalies/service/{subscriptionId}
 */

import React, { useState, useMemo, useContext } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceDot,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import {
  AlertTriangle,
  TrendingDown,
  TrendingUp,
  RefreshCw,
  SlidersHorizontal,
  Info,
  ChevronDown,
  ChevronUp,
  X,
  Zap,
} from 'lucide-react';
import { useAnomalyData } from '../hooks/useAnomalyData';

// ── Try to pick up the subscription from app context if available ─────────────
let SubscriptionContext;
try {
  ({ SubscriptionContext } = require('../context/SubscriptionContext'));
} catch {
  SubscriptionContext = null;
}

function useSubscriptionId() {
  const ctx = SubscriptionContext ? useContext(SubscriptionContext) : null; // eslint-disable-line react-hooks/rules-of-hooks
  return ctx?.subscriptionId ?? ctx?.activeSubscription ?? null;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmt = (n, currency = 'CAD') =>
  new Intl.NumberFormat('en-CA', { style: 'currency', currency, maximumFractionDigits: 0 }).format(n);

const fmtDate = (iso) => {
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString('en-CA', { month: 'short', day: 'numeric' });
};

const SEVERITY_COLOUR = {
  high: { bg: 'bg-red-50 dark:bg-red-900/20', border: 'border-red-200 dark:border-red-800', text: 'text-red-700 dark:text-red-300', badge: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300' },
  medium: { bg: 'bg-amber-50 dark:bg-amber-900/20', border: 'border-amber-200 dark:border-amber-800', text: 'text-amber-700 dark:text-amber-300', badge: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300' },
};

// ── Skeleton ──────────────────────────────────────────────────────────────────
function Skeleton({ className = '' }) {
  return <div className={`animate-pulse rounded bg-gray-200 dark:bg-gray-700 ${className}`} />;
}

// ── KPI card ──────────────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, icon: Icon, accent }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-3 shadow-sm">
      <div className={`mt-0.5 rounded-lg p-2 ${accent}`}>
        <Icon size={16} />
      </div>
      <div>
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400">{label}</p>
        <p className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">{value}</p>
        {sub && <p className="text-xs text-gray-400 dark:text-gray-500">{sub}</p>}
      </div>
    </div>
  );
}

// ── Custom chart tooltip ───────────────────────────────────────────────────────
function CustomTooltip({ active, payload, label, anomalyDates, currency }) {
  if (!active || !payload?.length) return null;
  const cost = payload[0]?.value;
  const isAnomaly = anomalyDates.has(label);
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 shadow-lg text-sm">
      <p className="font-semibold text-gray-700 dark:text-gray-200">{fmtDate(label)}</p>
      <p className="tabular-nums text-gray-600 dark:text-gray-300">{fmt(cost, currency)}</p>
      {isAnomaly && <p className="text-red-500 font-medium mt-0.5">⚠ Anomaly detected</p>}
    </div>
  );
}

// ── Anomaly alert row ──────────────────────────────────────────────────────────
function AnomalyAlert({ anomaly, currency, onDismiss }) {
  const [expanded, setExpanded] = useState(false);
  const s = SEVERITY_COLOUR[anomaly.severity] ?? SEVERITY_COLOUR.medium;
  const isSpike = anomaly.direction === 'spike';
  const deltaPct = anomaly.baseline_mean
    ? (((anomaly.actual_cost - anomaly.baseline_mean) / anomaly.baseline_mean) * 100).toFixed(1)
    : '—';

  return (
    <div className={`rounded-xl border ${s.border} ${s.bg} transition-all`}>
      <div className="flex items-center justify-between gap-3 px-4 py-3">
        <div className="flex items-center gap-3 min-w-0">
          {isSpike
            ? <TrendingUp size={16} className={s.text} />
            : <TrendingDown size={16} className={s.text} />}
          <div className="min-w-0">
            <span className="font-semibold text-sm text-gray-900 dark:text-gray-50">
              {fmtDate(anomaly.date)}
            </span>
            <span className={`ml-2 rounded-full px-2 py-0.5 text-xs font-medium ${s.badge}`}>
              {anomaly.severity.toUpperCase()}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="tabular-nums text-sm font-semibold text-gray-800 dark:text-gray-100">
            {fmt(anomaly.actual_cost, currency)}
          </span>
          <span className={`text-xs font-medium tabular-nums ${isSpike ? 'text-red-500' : 'text-teal-600'}`}>
            {isSpike ? '+' : ''}{deltaPct}%
          </span>
          <button
            onClick={() => setExpanded((e) => !e)}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            aria-label="Toggle detail"
          >
            {expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
          </button>
          <button
            onClick={() => onDismiss(anomaly.date)}
            className="text-gray-300 hover:text-gray-500 dark:hover:text-gray-400"
            aria-label="Dismiss anomaly"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-gray-200 dark:border-gray-700 px-4 pb-3 pt-2 grid grid-cols-3 gap-4 text-xs">
          <div>
            <p className="text-gray-500 dark:text-gray-400">Baseline mean</p>
            <p className="font-semibold tabular-nums text-gray-800 dark:text-gray-100">
              {fmt(anomaly.baseline_mean, currency)}
            </p>
          </div>
          <div>
            <p className="text-gray-500 dark:text-gray-400">Std deviation</p>
            <p className="font-semibold tabular-nums text-gray-800 dark:text-gray-100">
              {fmt(anomaly.baseline_stddev, currency)}
            </p>
          </div>
          <div>
            <p className="text-gray-500 dark:text-gray-400">Z-score</p>
            <p className="font-semibold tabular-nums text-gray-800 dark:text-gray-100">
              {anomaly.z_score.toFixed(2)}σ
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Service anomaly table ──────────────────────────────────────────────────────
function ServiceAnomalyTable({ anomalies, currency }) {
  if (!anomalies?.length) return null;
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden shadow-sm">
      <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700">
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Per-service anomalies</h3>
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
          Services with abnormal spend in the inspection window, ranked by z-score
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 dark:border-gray-700 text-left">
              {['Service', 'Date', 'Actual', 'Baseline', 'Z-score', 'Direction', 'Severity'].map((h) => (
                <th key={h} className="px-4 py-2 text-xs font-semibold text-gray-500 dark:text-gray-400">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {anomalies.map((a, i) => {
              const s = SEVERITY_COLOUR[a.severity] ?? SEVERITY_COLOUR.medium;
              return (
                <tr key={i} className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors">
                  <td className="px-4 py-2.5 font-medium text-gray-800 dark:text-gray-100 whitespace-nowrap">{a.service_name}</td>
                  <td className="px-4 py-2.5 text-gray-600 dark:text-gray-300 tabular-nums whitespace-nowrap">{fmtDate(a.date)}</td>
                  <td className="px-4 py-2.5 tabular-nums text-gray-800 dark:text-gray-100 whitespace-nowrap">{fmt(a.actual_cost, currency)}</td>
                  <td className="px-4 py-2.5 tabular-nums text-gray-500 dark:text-gray-400 whitespace-nowrap">{fmt(a.baseline_mean, currency)}</td>
                  <td className="px-4 py-2.5 tabular-nums font-semibold text-gray-800 dark:text-gray-100">{a.z_score.toFixed(2)}σ</td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-flex items-center gap-1 text-xs font-medium ${a.direction === 'spike' ? 'text-red-500' : 'text-teal-600'}`}>
                      {a.direction === 'spike' ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                      {a.direction}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${s.badge}`}>
                      {a.severity}
                    </span>
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

// ── Controls panel ─────────────────────────────────────────────────────────────
function ControlsPanel({ subId, setSubId, params, setParams, onRefresh, loading }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm">
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2">
          <label className="text-sm font-medium text-gray-700 dark:text-gray-300" htmlFor="sub-input">
            Subscription ID
          </label>
          <input
            id="sub-input"
            type="text"
            value={subId}
            onChange={(e) => setSubId(e.target.value)}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            className="ml-2 rounded-lg border border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 px-3 py-1.5 text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 w-80"
          />
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setOpen((o) => !o)}
            className="flex items-center gap-1.5 rounded-lg border border-gray-200 dark:border-gray-600 px-3 py-1.5 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          >
            <SlidersHorizontal size={14} />
            Parameters
          </button>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="flex items-center gap-1.5 rounded-lg bg-teal-600 hover:bg-teal-700 disabled:opacity-50 px-3 py-1.5 text-sm font-medium text-white transition-colors"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            {loading ? 'Loading…' : 'Analyze'}
          </button>
        </div>
      </div>

      {open && (
        <div className="border-t border-gray-100 dark:border-gray-700 px-4 py-3 grid grid-cols-3 gap-6">
          {[
            { key: 'window_days', label: 'Baseline window', min: 7, max: 90, step: 1, unit: 'days', help: 'Rolling window used to compute the mean and std-dev baseline.' },
            { key: 'lookback_days', label: 'Inspect window', min: 1, max: 30, step: 1, unit: 'days', help: 'How many recent days to check for anomalies.' },
            { key: 'threshold_sigma', label: 'Z-score threshold', min: 1.0, max: 5.0, step: 0.1, unit: 'σ', help: 'Minimum z-score to flag a day as anomalous.' },
          ].map(({ key, label, min, max, step, unit, help }) => (
            <div key={key}>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-medium text-gray-600 dark:text-gray-400">{label}</label>
                <span className="text-xs tabular-nums font-semibold text-teal-600 dark:text-teal-400">
                  {params[key]}{unit}
                </span>
              </div>
              <input
                type="range"
                min={min} max={max} step={step}
                value={params[key]}
                onChange={(e) => setParams((p) => ({ ...p, [key]: parseFloat(e.target.value) }))}
                className="w-full accent-teal-600"
              />
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{help}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Empty state ────────────────────────────────────────────────────────────────
function EmptyState({ message }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-gray-400 dark:text-gray-500">
      <Zap size={36} strokeWidth={1.5} />
      <p className="text-sm font-medium">{message || 'No anomalies detected in the selected window.'}</p>
      <p className="text-xs">Try widening the baseline window or lowering the z-score threshold.</p>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function CostAnomalyDetector() {
  const ctxSubId = useSubscriptionId();
  const [subId, setSubId] = useState(ctxSubId ?? '');
  const [dismissed, setDismissed] = useState(new Set());
  const [params, setParams] = useState({
    window_days: 30,
    lookback_days: 7,
    threshold_sigma: 2.0,
  });

  const { daily, service, loading, error, refetch } = useAnomalyData(subId, params, {
    window_days: 21,
    threshold_sigma: 2.5,
  });

  // Build chart data: merge series with anomaly flag
  const { chartData, anomalyDates, currency } = useMemo(() => {
    if (!daily?.series) return { chartData: [], anomalyDates: new Set(), currency: 'CAD' };
    const adates = new Set((daily.anomalies ?? []).map((a) => a.date));
    const cur = daily.billing_currency ?? 'CAD';
    const data = daily.series.map((s) => ({
      date: s.date,
      cost: s.cost ?? s.total,
      anomaly: adates.has(s.date) ? (s.cost ?? s.total) : null,
    }));
    return { chartData: data, anomalyDates: adates, currency: cur };
  }, [daily]);

  const visibleAnomalies = useMemo(
    () => (daily?.anomalies ?? []).filter((a) => !dismissed.has(a.date)),
    [daily, dismissed],
  );

  const highCount = visibleAnomalies.filter((a) => a.severity === 'high').length;
  const medCount = visibleAnomalies.filter((a) => a.severity === 'medium').length;
  const totalSpend = chartData.reduce((sum, d) => sum + (d.cost ?? 0), 0);

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 px-4 py-6 md:px-8">
      {/* Page header */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-1">
          <AlertTriangle size={20} className="text-teal-600" />
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-50">Cost Anomaly Detector</h1>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Rolling z-score analysis of daily Azure spend — flags unusual spikes and drops against the baseline window.
        </p>
      </div>

      {/* Controls */}
      <div className="mb-5">
        <ControlsPanel
          subId={subId}
          setSubId={setSubId}
          params={params}
          setParams={setParams}
          onRefresh={refetch}
          loading={loading}
        />
      </div>

      {/* Error banner */}
      {error && (
        <div className="mb-5 flex items-start gap-2 rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* KPI bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        {loading ? (
          Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-xl" />)
        ) : (
          <>
            <KpiCard
              label="Total anomalies"
              value={daily?.anomaly_count ?? 0}
              sub={`in ${params.lookback_days}d window`}
              icon={AlertTriangle}
              accent="bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400"
            />
            <KpiCard
              label="High severity"
              value={highCount}
              sub="z-score ≥ 3σ"
              icon={TrendingUp}
              accent="bg-orange-100 text-orange-600 dark:bg-orange-900/40 dark:text-orange-400"
            />
            <KpiCard
              label="Medium severity"
              value={medCount}
              sub="z-score ≥ 2σ"
              icon={Info}
              accent="bg-amber-100 text-amber-600 dark:bg-amber-900/40 dark:text-amber-400"
            />
            <KpiCard
              label={`Total spend (${params.window_days}d)`}
              value={chartData.length ? fmt(totalSpend, currency) : '—'}
              sub={`${chartData.length} days of data`}
              icon={Zap}
              accent="bg-teal-100 text-teal-600 dark:bg-teal-900/40 dark:text-teal-400"
            />
          </>
        )}
      </div>

      {/* Time-series chart */}
      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm mb-5 p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Daily cost — {params.window_days}d baseline</h2>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              Red dots mark days where spend deviated ≥ {params.threshold_sigma}σ from the rolling mean
            </p>
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
            <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5 bg-teal-500" /> Daily cost</span>
            <span className="flex items-center gap-1"><span className="inline-block w-2.5 h-2.5 rounded-full bg-red-500" /> Anomaly</span>
          </div>
        </div>

        {loading ? (
          <Skeleton className="h-64 rounded-lg" />
        ) : chartData.length === 0 ? (
          <div className="h-64 flex items-center justify-center text-sm text-gray-400 dark:text-gray-500">
            No data — enter a subscription ID and click Analyze
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(156,163,175,0.2)" />
              <XAxis
                dataKey="date"
                tickFormatter={fmtDate}
                tick={{ fontSize: 11 }}
                interval="preserveStartEnd"
                stroke="rgba(156,163,175,0.4)"
              />
              <YAxis
                tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                tick={{ fontSize: 11 }}
                stroke="rgba(156,163,175,0.4)"
                width={52}
              />
              <Tooltip content={<CustomTooltip anomalyDates={anomalyDates} currency={currency} />} />
              <Line
                type="monotone"
                dataKey="cost"
                stroke="#0d9488"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
              />
              {/* Anomaly reference dots */}
              {chartData
                .filter((d) => anomalyDates.has(d.date))
                .map((d) => (
                  <ReferenceDot
                    key={d.date}
                    x={d.date}
                    y={d.cost}
                    r={5}
                    fill="#ef4444"
                    stroke="#fff"
                    strokeWidth={2}
                  />
                ))}
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Anomaly alert list */}
      <div className="mb-5">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">
            Anomaly alerts
            {visibleAnomalies.length > 0 && (
              <span className="ml-2 rounded-full bg-red-100 text-red-600 dark:bg-red-900/40 dark:text-red-400 px-2 py-0.5 text-xs font-medium">
                {visibleAnomalies.length}
              </span>
            )}
          </h2>
          {dismissed.size > 0 && (
            <button
              onClick={() => setDismissed(new Set())}
              className="text-xs text-teal-600 hover:underline"
            >
              Restore {dismissed.size} dismissed
            </button>
          )}
        </div>

        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-14 rounded-xl" />)}
          </div>
        ) : visibleAnomalies.length === 0 ? (
          <EmptyState message={daily ? 'No anomalies detected in the selected window.' : undefined} />
        ) : (
          <div className="space-y-2">
            {visibleAnomalies.map((a) => (
              <AnomalyAlert
                key={a.date}
                anomaly={a}
                currency={currency}
                onDismiss={(date) => setDismissed((d) => new Set([...d, date]))}
              />
            ))}
          </div>
        )}
      </div>

      {/* Service anomaly table */}
      {!loading && service?.service_anomalies?.length > 0 && (
        <ServiceAnomalyTable anomalies={service.service_anomalies} currency={currency} />
      )}
      {loading && <Skeleton className="h-48 rounded-xl" />}
    </div>
  );
}
