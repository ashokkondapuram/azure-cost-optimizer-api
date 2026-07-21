/**
 * Demand Forecaster
 *
 * Data: GET /costs/demand-forecast (Azure Cost Management history + forecast API)
 */
import React, { useState, useCallback, useMemo, useEffect } from 'react';
import {
  ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine, ResponsiveContainer,
} from 'recharts';
import { Info } from 'lucide-react';
import { buildForecastChartData, fetchDemandForecast } from '../api/demandForecaster';
import AdvancedToolLayout, { useAdvancedSubscription } from '../components/advanced/AdvancedToolLayout';
import { CHART_AXIS_TICK, CHART_GRID, CHART_PALETTE } from '../components/wiz/charts/wizChartColors';
import WizChartTooltip from '../components/wiz/charts/WizChartTooltip';

const fmt = (n, cur = 'CAD') =>
  n != null ? new Intl.NumberFormat('en-CA', { style: 'currency', currency: cur, maximumFractionDigits: 0 }).format(n) : '—';

const fmtMonth = (ym) => {
  try {
    const [y, m] = ym.split('-');
    return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString('en-CA', { month: 'short', year: '2-digit' });
  } catch { return ym; }
};

function Skeleton({ className = '' }) {
  return <div className={`dashboard-kpi-skeleton ${className}`} />;
}

function KpiCard({ label, value, sub, accent }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className={`stat-value ${accent || ''}`}>{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

function ForecastTooltip({ active, payload, label, currency }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="wiz-chart-tooltip" role="tooltip">
      <div className="wiz-chart-tooltip__label">{fmtMonth(label)}</div>
      {payload.map((p) => (
        <div key={p.name} className="wiz-chart-tooltip__value" style={{ color: p.color }}>
          {p.name === 'predicted_spend' ? 'Azure forecast' : 'Actual'}: {fmt(p.value, currency)}
        </div>
      ))}
    </div>
  );
}

export default function DemandForecaster() {
  const { subscription } = useAdvancedSubscription();
  const [histMonths, setHistMonths] = useState(6);
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!subscription?.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchDemandForecast(subscription, histMonths);
      setPayload(data);
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [subscription, histMonths]);

  useEffect(() => {
    load();
  }, [load]);

  const timeline = payload?.timeline ?? [];
  const forecast = payload?.forecast ?? [];
  const currency = payload?.billing_currency ?? 'CAD';

  const chartData = useMemo(
    () => buildForecastChartData(timeline, forecast),
    [timeline, forecast],
  );

  const projectedMonthEnd = payload?.projected_month_end;
  const deltaPct = payload?.delta_pct_vs_last_month;
  const trendLabel = deltaPct == null
    ? '—'
    : deltaPct > 5
      ? `↑ +${deltaPct}% vs last month`
      : deltaPct < -5
        ? `↓ ${deltaPct}% vs last month`
        : 'Flat vs last month';
  const trendColour = deltaPct > 5 ? 'text-danger' : deltaPct < -5 ? 'text-success' : '';

  const lastHistoricalMonth = timeline[timeline.length - 1]?.month;

  return (
    <AdvancedToolLayout
      title="Demand forecaster"
      pageScope="demandForecaster"
      iconKey="demandForecaster"
      iconRoute="/demand-forecaster"
      onRefresh={load}
      loading={loading}
      error={error}
      errorTitle="Could not load demand forecast"
    >
      <div className="flex flex-wrap items-center gap-3 mb-5">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">History:</span>
          {[3, 6, 9, 12].map((n) => (
            <button
              key={n}
              type="button"
              onClick={() => setHistMonths(n)}
              className={`rounded-lg px-2.5 py-1 text-xs font-medium ${
                histMonths === n ? 'bg-teal-600 text-white' : 'border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              {n}m
            </button>
          ))}
        </div>
      </div>

      {(loading || payload) && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
          {loading ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-xl" />) : (
            <>
              <KpiCard
                label="Projected month end"
                value={fmt(projectedMonthEnd, currency)}
                sub="Azure Cost Management forecast"
                accent="text-gray-900 dark:text-gray-50"
              />
              <KpiCard
                label="Vs last month"
                value={trendLabel}
                sub="projected change"
                accent={trendColour}
              />
              <KpiCard
                label="History months"
                value={timeline.length || '—'}
                sub={`${histMonths}m window requested`}
                accent="text-gray-800 dark:text-gray-100"
              />
              <KpiCard
                label="Data source"
                value="Azure"
                sub="Cost Management API"
                accent="text-gray-700 dark:text-gray-300"
              />
            </>
          )}
        </div>
      )}

      {(loading || chartData.length > 0) && (
        <div className="wiz-chart-card" style={{ marginBottom: '1.25rem' }}>
          <div className="wiz-chart-card__head">
            <div>
              <h3 className="wiz-chart-card__title">Historical spend + Azure forecast</h3>
              <p className="wiz-chart-card__sub">Solid bars = actual · Dashed line = Azure forecast</p>
            </div>
            <span className="wiz-pill wiz-pill--ok">Azure forecast</span>
          </div>
          {loading ? <Skeleton className="h-60" /> : (
            <div className="wiz-chart-body">
            <ResponsiveContainer width="100%" height={240}>
              <ComposedChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid {...CHART_GRID} />
                <XAxis dataKey="month" tickFormatter={fmtMonth} tick={CHART_AXIS_TICK} stroke="var(--chart-axis)" />
                <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} tick={CHART_AXIS_TICK} stroke="var(--chart-axis)" width={52} />
                <Tooltip content={<ForecastTooltip currency={currency} />} />
                {lastHistoricalMonth && (
                  <ReferenceLine
                    x={lastHistoricalMonth}
                    stroke="var(--chart-grid)"
                    strokeDasharray="4 4"
                    label={{ value: 'today', fontSize: 10, fill: 'var(--chart-axis)', position: 'insideTopRight' }}
                  />
                )}
                <Bar dataKey="total_spend" fill={CHART_PALETTE[2]} opacity={0.8} radius={[3, 3, 0, 0]} name="total_spend" />
                <Line
                  dataKey="predicted_spend"
                  stroke={CHART_PALETTE[7]}
                  strokeWidth={2}
                  strokeDasharray="6 3"
                  dot={{ r: 4, fill: CHART_PALETTE[7] }}
                  name="predicted_spend"
                  connectNulls
                />
              </ComposedChart>
            </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {!loading && forecast.length > 0 && (
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm overflow-hidden mb-5">
          <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-700">
            <h2 className="text-sm font-semibold text-gray-800 dark:text-gray-100">Forecast breakdown</h2>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 dark:border-gray-700">
                {['Month', 'Azure forecast', 'Vs last actual'].map((h) => (
                  <th key={h} className="px-4 py-2 text-left text-xs font-semibold text-gray-500 dark:text-gray-400">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {forecast.map((row) => {
                const lastActual = timeline[timeline.length - 1]?.total_spend;
                const delta = lastActual != null ? row.predicted_spend - lastActual : null;
                const pct = lastActual ? ((delta / lastActual) * 100).toFixed(1) : null;
                return (
                  <tr key={row.month} className="border-b border-gray-50 dark:border-gray-800">
                    <td className="px-4 py-2.5 font-medium text-gray-800 dark:text-gray-100">{fmtMonth(row.month)}</td>
                    <td className="px-4 py-2.5 tabular-nums font-semibold text-gray-800 dark:text-gray-100">{fmt(row.predicted_spend, currency)}</td>
                    <td className={`px-4 py-2.5 tabular-nums font-semibold ${delta < 0 ? 'text-teal-600' : delta > 0 ? 'text-red-500' : 'text-gray-400'}`}>
                      {delta != null ? `${delta >= 0 ? '+' : ''}${fmt(delta, currency)} (${pct}%)` : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {!loading && payload && (
        <div className="flex items-start gap-2 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-3 text-xs text-gray-500 dark:text-gray-400">
          <Info size={13} className="mt-0.5 shrink-0 text-gray-400" />
          <p>
            Historical months come from Azure Cost Management actual-cost queries. The forecast is Azure&apos;s projected
            end-of-month spend for the current billing period — not a local regression model. Azure forecasts the current
            month only; multi-month projections beyond that are not available from the API.
          </p>
        </div>
      )}
    </AdvancedToolLayout>
  );
}
