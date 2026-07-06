/**
 * Demand Forecaster
 *
 * ┌─ Horizon selector (1m / 3m / 6m) + confidence indicator ─────┐
 * ├─ Combined chart: historical (solid) + forecast (dashed)       ┤
 * ├─ Forecast table with monthly predicted spend                   ┤
 * └─ R² explainer + methodology note                               ┘
 *
 * Data: GET /savings/month-over-month/{id}  (historical)
 * Math: client-side weighted linear regression via demandForecaster.js
 */
import React, { useState, useCallback, useContext, useMemo } from 'react';
import {
  ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ReferenceLine, ResponsiveContainer,
} from 'recharts';
import { TrendingUp, RefreshCw, AlertTriangle, Info } from 'lucide-react';
import { fetchForecastData, computeForecast } from '../api/demandForecaster';

let SubscriptionContext;
try { ({ SubscriptionContext } = require('../context/SubscriptionContext')); } catch { SubscriptionContext = null; }
function useCtxSub() {
  const ctx = SubscriptionContext ? useContext(SubscriptionContext) : null; // eslint-disable-line
  return ctx?.subscriptionId ?? ctx?.activeSubscription ?? null;
}

const fmt = (n, cur = 'CAD') =>
  n != null ? new Intl.NumberFormat('en-CA', { style: 'currency', currency: cur, maximumFractionDigits: 0 }).format(n) : '—';

const fmtMonth = (ym) => {
  try {
    const [y, m] = ym.split('-');
    return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString('en-CA', { month: 'short', year: '2-digit' });
  } catch { return ym; }
};

function Skeleton({ className = '' }) {
  return <div className={`animate-pulse rounded bg-gray-200 dark:bg-gray-700 ${className}`} />;
}

function KpiCard({ label, value, sub, accent }) {
  return (
    <div className="flex flex-col rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-3 shadow-sm">
      <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{label}</p>
      <p className={`text-lg font-semibold tabular-nums ${accent}`}>{value}</p>
      {sub && <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">{sub}</p>}
    </div>
  );
}

function R2Badge({ r2 }) {
  const label = r2 >= 0.8 ? 'High confidence' : r2 >= 0.5 ? 'Moderate confidence' : 'Low confidence';
  const colour = r2 >= 0.8 ? 'bg-teal-100 text-teal-700 dark:bg-teal-900/40 dark:text-teal-300'
    : r2 >= 0.5 ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
    : 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300';
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${colour}`}>
      R² = {r2} · {label}
    </span>
  );
}

function ForecastTooltip({ active, payload, label, currency }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 shadow-lg text-sm">
      <p className="font-semibold text-gray-700 dark:text-gray-200 mb-1">{fmtMonth(label)}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }} className="tabular-nums">
          {p.name === 'predicted_spend' ? 'Forecast' : 'Actual'}: {fmt(p.value, currency)}
        </p>
      ))}
    </div>
  );
}

export default function DemandForecaster() {
  const ctxSub = useCtxSub();
  const [subId, setSubId] = useState(ctxSub ?? '');
  const [histMonths, setHistMonths] = useState(6);
  const [horizon, setHorizon] = useState(3);
  const [timeline, setTimeline] = useState(null);
  const [currency, setCurrency] = useState('CAD');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!subId.trim()) return;
    setLoading(true); setError(null);
    try {
      const d = await fetchForecastData(subId, histMonths);
      setTimeline(d.timeline ?? []);
      setCurrency(d.billing_currency ?? 'CAD');
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [subId, histMonths]);

  const result = useMemo(() => {
    if (!timeline?.length) return null;
    return computeForecast(timeline, horizon);
  }, [timeline, horizon]);

  const chartData = useMemo(() => {
    if (!timeline) return [];
    const hist = timeline.map((t) => ({ month: t.month, total_spend: t.total_spend, is_forecast: false }));
    const fore = result?.forecast ?? [];
    return [...hist, ...fore];
  }, [timeline, result]);

  const nextMonthForecast = result?.forecast?.[0]?.predicted_spend;
  const trend = result?.slope ?? 0;
  const trendLabel = trend > 500 ? `↑ +${fmt(trend, currency)}/mo trend` : trend < -500 ? `↓ ${fmt(trend, currency)}/mo trend` : 'Flat trend';
  const trendColour = trend > 500 ? 'text-red-500' : trend < -500 ? 'text-teal-600' : 'text-gray-500';

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 px-4 py-6 md:px-8">
      <div className="mb-5">
        <div className="flex items-center gap-2 mb-1">
          <TrendingUp size={20} className="text-teal-600" />
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-50">Demand Forecaster</h1>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Weighted linear regression over historical monthly spend — projected forward.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-5">
        <input type="text" value={subId} onChange={(e) => setSubId(e.target.value)}
          placeholder="Subscription ID"
          className="rounded-lg border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-1.5 text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-teal-500 w-80"
        />
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">History:</span>
          {[3,6,9,12].map((n) => (
            <button key={n} onClick={() => setHistMonths(n)}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
                histMonths === n ? 'bg-teal-600 text-white' : 'border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}>{n}m</button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">Forecast:</span>
          {[1,3,6].map((n) => (
            <button key={n} onClick={() => setHorizon(n)}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
                horizon === n ? 'bg-indigo-600 text-white' : 'border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}>{n}m</button>
          ))}
        </div>
        <button onClick={load} disabled={loading}
          className="flex items-center gap-1.5 rounded-lg bg-teal-600 hover:bg-teal-700 disabled:opacity-50 px-4 py-1.5 text-sm font-medium text-white transition-colors">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Loading…' : 'Load'}
        </button>
      </div>

      {error && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />{error}
        </div>
      )}

      {/* KPIs */}
      {(loading || result) && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
          {loading ? Array.from({length:4}).map((_,i)=><Skeleton key={i} className="h-16 rounded-xl" />) : (
            <>
              <KpiCard label="Next month forecast" value={fmt(nextMonthForecast, currency)}
                sub="predicted spend" accent="text-gray-900 dark:text-gray-50" />
              <KpiCard label="Monthly trend" value={trendLabel}
                sub="per-month change" accent={trendColour} />
              <KpiCard label="Model fit (R²)" value={result?.r2 ?? '—'}
                sub={result?.r2 >= 0.8 ? 'High confidence' : result?.r2 >= 0.5 ? 'Moderate' : 'Low — more data needed'}
                accent="text-gray-800 dark:text-gray-100" />
              <KpiCard label="Forecast horizon" value={`${horizon} month${horizon > 1 ? 's' : ''}`}
                sub={`${histMonths}m history used`} accent="text-gray-700 dark:text-gray-300" />
            </>
          )}
        </div>
      )}

      {/* Chart */}
      {(loading || chartData.length > 0) && (
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm p-4 mb-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Historical spend + forecast</h2>
            {result && <R2Badge r2={result.r2} />}
          </div>
          {loading ? <Skeleton className="h-60" /> : (
            <ResponsiveContainer width="100%" height={240}>
              <ComposedChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(156,163,175,0.2)" />
                <XAxis dataKey="month" tickFormatter={fmtMonth} tick={{ fontSize: 11 }} stroke="rgba(156,163,175,0.4)" />
                <YAxis tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} tick={{ fontSize: 11 }} stroke="rgba(156,163,175,0.4)" width={52} />
                <Tooltip content={<ForecastTooltip currency={currency} />} />
                <ReferenceLine
                  x={timeline?.[timeline.length - 1]?.month}
                  stroke="rgba(156,163,175,0.5)" strokeDasharray="4 4"
                  label={{ value: 'today', fontSize: 10, fill: '#9ca3af', position: 'insideTopRight' }}
                />
                {/* Historical bars */}
                <Bar dataKey="total_spend" fill="#0d9488" opacity={0.75} radius={[3,3,0,0]}
                  name="total_spend"
                  data={chartData.filter((d) => !d.is_forecast)}
                />
                {/* Forecast line */}
                <Line dataKey="predicted_spend" stroke="#6366f1" strokeWidth={2}
                  strokeDasharray="6 3" dot={{ r: 4, fill: '#6366f1' }}
                  name="predicted_spend"
                  data={chartData.filter((d) => d.is_forecast)}
                />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      )}

      {/* Forecast table */}
      {!loading && result?.forecast?.length > 0 && (
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm overflow-hidden mb-5">
          <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700">
            <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Forecast breakdown</h2>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 dark:border-gray-700">
                {['Month','Predicted spend','vs last actual','Trend'].map((h) => (
                  <th key={h} className="px-4 py-2 text-left text-xs font-semibold text-gray-500 dark:text-gray-400">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.forecast.map((row, i) => {
                const lastActual = timeline?.[timeline.length - 1]?.total_spend;
                const delta = lastActual ? row.predicted_spend - lastActual : null;
                const pct = lastActual ? ((delta / lastActual) * 100).toFixed(1) : null;
                return (
                  <tr key={i} className="border-b border-gray-50 dark:border-gray-800">
                    <td className="px-4 py-2.5 font-medium text-gray-800 dark:text-gray-100">{fmtMonth(row.month)}</td>
                    <td className="px-4 py-2.5 tabular-nums font-semibold text-gray-800 dark:text-gray-100">{fmt(row.predicted_spend, currency)}</td>
                    <td className={`px-4 py-2.5 tabular-nums font-semibold ${delta < 0 ? 'text-teal-600' : delta > 0 ? 'text-red-500' : 'text-gray-400'}`}>
                      {delta != null ? `${delta >= 0 ? '+' : ''}${fmt(delta, currency)} (${pct}%)` : '—'}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`text-xs font-medium ${
                        i === 0 ? 'text-gray-500' : row.predicted_spend > result.forecast[i-1].predicted_spend ? 'text-red-400' : 'text-teal-500'
                      }`}>
                        {i === 0 ? '' : row.predicted_spend > result.forecast[i-1].predicted_spend ? '↑ Rising' : '↓ Falling'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Methodology note */}
      {!loading && result && (
        <div className="flex items-start gap-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-3 text-xs text-gray-500 dark:text-gray-400">
          <Info size={13} className="mt-0.5 shrink-0 text-gray-400" />
          <p>Forecasts use weighted linear regression — recent months are weighted higher. R² measures how well the trend line fits historical data (1.0 = perfect fit). Forecasts are estimates only and may not account for seasonal patterns or one-off spikes.</p>
        </div>
      )}

      {!loading && !timeline && !error && (
        <div className="flex flex-col items-center justify-center py-20 text-gray-400 dark:text-gray-500 gap-3">
          <TrendingUp size={40} strokeWidth={1.5} />
          <p className="text-sm font-medium">Enter a subscription ID and click Load</p>
        </div>
      )}
    </div>
  );
}
