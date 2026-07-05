import React, { useMemo, useState } from 'react';
import {
  LineChart, Line, BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Brush,
} from 'recharts';
import { formatCurrency } from '../../utils/format';
import { formatChartAxis } from '../../utils/costCurrency';
import { barColorByPct } from '../../utils/visualPolish';

export function CostDailyTrendChart({
  data,
  currency,
  fieldLabel,
  compareLabel,
  loading,
}) {
  const [hidden, setHidden] = useState({});
  const [brushRange, setBrushRange] = useState(null);

  const chartData = useMemo(() => {
    if (!brushRange) return data;
    const [start, end] = brushRange;
    return data.slice(start, end + 1);
  }, [data, brushRange]);

  const hasCompare = data.some((r) => r.compareCost != null);

  if (loading) {
    return (
      <div className="cost-explorer-chart-loading" role="status">
        <div className="spin" />
        <p>Loading daily costs…</p>
      </div>
    );
  }
  if (!data.length) return null;

  const toggleSeries = (key) => {
    setHidden((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="cost-trend-chart">
      <div className="cost-trend-chart__toolbar">
        {hasCompare && (
          <div className="cost-trend-chart__legend-toggles" role="group" aria-label="Chart series">
            <button
              type="button"
              className={`cost-trend-chart__legend-btn${hidden.current ? '' : ' cost-trend-chart__legend-btn--active'}`}
              onClick={() => toggleSeries('current')}
            >
              Current period
            </button>
            <button
              type="button"
              className={`cost-trend-chart__legend-btn${hidden.compare ? '' : ' cost-trend-chart__legend-btn--active'}`}
              onClick={() => toggleSeries('compare')}
            >
              {compareLabel || 'Previous period'}
            </button>
          </div>
        )}
        {brushRange && (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setBrushRange(null)}
          >
            Reset zoom
          </button>
        )}
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="dateLabel" tick={{ fill: 'var(--text3)', fontSize: 10 }} interval="preserveStartEnd" />
          <YAxis tick={{ fill: 'var(--text3)', fontSize: 10 }} tickFormatter={(v) => formatChartAxis(v, currency)} />
          <Tooltip
            contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 8 }}
            formatter={(value, name) => [
              formatCurrency(value, { currency }),
              name === 'compareCost' ? (compareLabel || 'Previous') : fieldLabel,
            ]}
            labelFormatter={(_, payload) => {
              const row = payload?.[0]?.payload;
              if (!row) return '';
              return row.compareDateLabel
                ? `${row.dateLabel} vs ${row.compareDateLabel}`
                : row.dateLabel;
            }}
          />
          {!hidden.current && (
            <Line type="monotone" dataKey="cost" name="cost" stroke="#0284c7" strokeWidth={2} dot={false} />
          )}
          {hasCompare && !hidden.compare && (
            <Line type="monotone" dataKey="compareCost" name="compareCost" stroke="#94a3b8" strokeWidth={2} dot={false} strokeDasharray="4 4" />
          )}
          <Brush
            dataKey="dateLabel"
            height={24}
            stroke="var(--border)"
            onChange={(range) => {
              if (range?.startIndex != null && range?.endIndex != null) {
                setBrushRange([range.startIndex, range.endIndex]);
              }
            }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function CostServiceBarChart({
  data,
  currency,
  fieldLabel,
  loading,
  colors,
}) {
  const [hiddenServices, setHiddenServices] = useState({});

  const visibleData = useMemo(
    () => data.filter((row) => !hiddenServices[row.name]),
    [data, hiddenServices],
  );

  if (loading) {
    return (
      <div className="cost-explorer-chart-loading" role="status">
        <div className="spin" />
        <p>Loading services…</p>
      </div>
    );
  }
  if (!data.length) return null;

  const maxCost = Math.max(...data.map((r) => r.cost || 0));

  return (
    <div className="cost-trend-chart">
      <div className="cost-trend-chart__series-toggles" role="group" aria-label="Service series">
        {data.slice(0, 8).map((row, i) => (
          <label key={row.name} className="cost-trend-chart__series-chip">
            <input
              type="checkbox"
              checked={!hiddenServices[row.name]}
              onChange={() => setHiddenServices((prev) => ({
                ...prev,
                [row.name]: !prev[row.name],
              }))}
            />
            <span
              className="cost-trend-chart__series-swatch"
              style={{ background: barColorByPct(maxCost > 0 ? (row.cost / maxCost) * 100 : 0) }}
              aria-hidden
            />
            {row.name.length > 16 ? `${row.name.slice(0, 15)}…` : row.name}
          </label>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={visibleData} layout="vertical" margin={{ left: 4, right: 12 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis type="number" tick={{ fill: 'var(--text3)', fontSize: 10 }} tickFormatter={(v) => formatChartAxis(v, currency)} />
          <YAxis
            type="category"
            dataKey="name"
            width={100}
            tick={{ fill: 'var(--text3)', fontSize: 10 }}
            tickFormatter={(v) => (v.length > 14 ? `${v.slice(0, 13)}…` : v)}
          />
          <Tooltip
            contentStyle={{ background: 'var(--bg2)', border: '1px solid var(--border)', borderRadius: 8 }}
            formatter={(value) => [formatCurrency(value, { currency }), fieldLabel]}
          />
          <Bar dataKey="cost" radius={[0, 4, 4, 0]}>
            {visibleData.map((row, i) => {
              const pct = maxCost > 0 ? (row.cost / maxCost) * 100 : 0;
              return (
                <Cell key={row.name} fill={barColorByPct(pct)} />
              );
            })}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
