import React, { useMemo, useState } from 'react';
import {
  LineChart, Line, BarChart, Bar, AreaChart, Area, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ComposedChart,
} from 'recharts';
import { formatCurrency } from '../../utils/format';
import { formatChartAxis } from '../../utils/costCurrency';
import { barColorByPct } from '../../utils/visualPolish';
import ChartBrushNavigator from '../charts/ChartBrushNavigator';
import { useChartBrushRange, useBrushedChartData } from '../../hooks/useChartBrushRange';

const COST_AREA_GRADIENT = 'costAreaGradient';
const COST_COMPARE_GRADIENT = 'costCompareGradient';
const CUMULATIVE_GRADIENT = 'costCumulativeGradient';

function ChartLoading({ message }) {
  return (
    <div className="cost-explorer-chart-loading" role="status">
      <div className="spin" />
      <p>{message}</p>
    </div>
  );
}

function chartTooltipStyle() {
  return {
    background: 'var(--bg2)',
    border: '1px solid var(--border)',
    borderRadius: 10,
    boxShadow: '0 8px 24px rgba(0,0,0,0.12)',
  };
}

export function CostDailyTrendChart({
  data,
  currency,
  fieldLabel,
  compareLabel,
  loading,
  variant = 'area',
}) {
  const [hidden, setHidden] = useState({});
  const {
    startIndex,
    endIndex,
    maxIndex,
    isZoomed,
    onBrushChange,
    resetBrush,
  } = useChartBrushRange(data.length);
  const chartData = useBrushedChartData(data, startIndex, endIndex, maxIndex);

  const hasCompare = data.some((r) => r.compareCost != null);

  if (loading) return <ChartLoading message="Loading daily costs…" />;
  if (!data.length) return null;

  const toggleSeries = (key) => {
    setHidden((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const ChartComponent = variant === 'line' ? LineChart : AreaChart;

  return (
    <div className="cost-trend-chart cost-trend-chart--daily">
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
        {isZoomed && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={resetBrush}>
            Reset zoom
          </button>
        )}
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <ChartComponent data={chartData} margin={{ top: 12, right: 12, left: 0, bottom: 4 }}>
          <defs>
            <linearGradient id={COST_AREA_GRADIENT} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#0284c7" stopOpacity={0.45} />
              <stop offset="100%" stopColor="#0284c7" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id={COST_COMPARE_GRADIENT} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#94a3b8" stopOpacity={0.25} />
              <stop offset="100%" stopColor="#94a3b8" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
          <XAxis dataKey="dateLabel" tick={{ fill: 'var(--text3)', fontSize: 10 }} interval="preserveStartEnd" />
          <YAxis tick={{ fill: 'var(--text3)', fontSize: 10 }} tickFormatter={(v) => formatChartAxis(v, currency)} />
          <Tooltip
            contentStyle={chartTooltipStyle()}
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
          {variant === 'area' && !hidden.current && (
            <Area
              type="monotone"
              dataKey="cost"
              name="cost"
              stroke="#0284c7"
              strokeWidth={2.5}
              fill={`url(#${COST_AREA_GRADIENT})`}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0 }}
            />
          )}
          {variant === 'line' && !hidden.current && (
            <Line type="monotone" dataKey="cost" name="cost" stroke="#0284c7" strokeWidth={2.5} dot={false} />
          )}
          {hasCompare && !hidden.compare && (
            variant === 'area' ? (
              <Area
                type="monotone"
                dataKey="compareCost"
                name="compareCost"
                stroke="#94a3b8"
                strokeWidth={2}
                strokeDasharray="5 4"
                fill={`url(#${COST_COMPARE_GRADIENT})`}
                dot={false}
              />
            ) : (
              <Line
                type="monotone"
                dataKey="compareCost"
                name="compareCost"
                stroke="#94a3b8"
                strokeWidth={2}
                dot={false}
                strokeDasharray="5 4"
              />
            )
          )}
        </ChartComponent>
      </ResponsiveContainer>
      <ChartBrushNavigator
        data={data}
        dataKey="dateLabel"
        valueKey="cost"
        startIndex={startIndex}
        endIndex={endIndex}
        onRangeChange={onBrushChange}
      />
    </div>
  );
}

export function CostCumulativeChart({ data, currency, fieldLabel, loading }) {
  const cumulative = useMemo(() => {
    let running = 0;
    return data.map((row) => {
      running += row.cost || 0;
      return { ...row, cumulative: running };
    });
  }, [data]);

  if (loading) return <ChartLoading message="Loading cumulative spend…" />;
  if (!cumulative.length) return null;

  return (
    <div className="cost-trend-chart cost-trend-chart--cumulative">
      <ResponsiveContainer width="100%" height={240}>
        <AreaChart data={cumulative} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={CUMULATIVE_GRADIENT} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#6366f1" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#6366f1" stopOpacity={0.03} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
          <XAxis dataKey="dateLabel" tick={{ fill: 'var(--text3)', fontSize: 10 }} interval="preserveEnd" />
          <YAxis tick={{ fill: 'var(--text3)', fontSize: 10 }} tickFormatter={(v) => formatChartAxis(v, currency)} />
          <Tooltip
            contentStyle={chartTooltipStyle()}
            formatter={(value) => [formatCurrency(value, { currency }), fieldLabel]}
          />
          <Area
            type="monotone"
            dataKey="cumulative"
            stroke="#6366f1"
            strokeWidth={2}
            fill={`url(#${CUMULATIVE_GRADIENT})`}
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function CostServiceMixDonut({ data, currency, total, loading, colors }) {
  if (loading) return <ChartLoading message="Loading service mix…" />;
  if (!data.length) return null;

  const palette = colors || ['#0284c7', '#0ea5e9', '#38bdf8', '#6366f1', '#8b5cf6', '#94a3b8'];

  return (
    <div className="cost-trend-chart cost-trend-chart--donut">
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={58}
            outerRadius={88}
            dataKey="cost"
            nameKey="name"
            paddingAngle={2}
            stroke="var(--border-subtle)"
          >
            {data.map((row, i) => (
              <Cell key={row.name} fill={palette[i % palette.length]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={chartTooltipStyle()}
            formatter={(value) => [formatCurrency(value, { currency }), 'Spend']}
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="cost-donut-center" aria-hidden>
        <strong>{formatCurrency(total, { currency, decimals: 0 })}</strong>
        <span>total</span>
      </div>
      <ul className="cost-donut-legend">
        {data.map((row, i) => {
          const share = total > 0 ? (row.cost / total) * 100 : 0;
          return (
            <li key={row.name}>
              <span className="cost-donut-legend__dot" style={{ background: palette[i % palette.length] }} />
              <span className="cost-donut-legend__name">{row.name}</span>
              <strong>{share >= 0.1 ? `${share.toFixed(1)}%` : '<0.1%'}</strong>
            </li>
          );
        })}
      </ul>
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

  if (loading) return <ChartLoading message="Loading services…" />;
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
              style={{ background: colors?.[i] || barColorByPct(maxCost > 0 ? (row.cost / maxCost) * 100 : 0) }}
              aria-hidden
            />
            {row.name.length > 16 ? `${row.name.slice(0, 15)}…` : row.name}
          </label>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={visibleData} layout="vertical" margin={{ left: 4, right: 12, top: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" horizontal={false} />
          <XAxis type="number" tick={{ fill: 'var(--text3)', fontSize: 10 }} tickFormatter={(v) => formatChartAxis(v, currency)} />
          <YAxis
            type="category"
            dataKey="name"
            width={108}
            tick={{ fill: 'var(--text3)', fontSize: 10 }}
            tickFormatter={(v) => (v.length > 14 ? `${v.slice(0, 13)}…` : v)}
          />
          <Tooltip
            contentStyle={chartTooltipStyle()}
            formatter={(value) => [formatCurrency(value, { currency }), fieldLabel]}
          />
          <Bar dataKey="cost" radius={[0, 6, 6, 0]} maxBarSize={22}>
            {visibleData.map((row, i) => {
              const pct = maxCost > 0 ? (row.cost / maxCost) * 100 : 0;
              return (
                <Cell key={row.name} fill={colors?.[i % colors.length] || barColorByPct(pct)} />
              );
            })}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function CostServiceColumnChart({ data, currency, fieldLabel, loading, colors }) {
  if (loading) return <ChartLoading message="Loading services…" />;
  if (!data.length) return null;

  const maxCost = Math.max(...data.map((r) => r.cost || 0));

  return (
    <div className="cost-trend-chart cost-trend-chart--columns">
      <ResponsiveContainer width="100%" height={260}>
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 24 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
          <XAxis
            dataKey="name"
            tick={{ fill: 'var(--text3)', fontSize: 9 }}
            interval={0}
            angle={-28}
            textAnchor="end"
            height={56}
            tickFormatter={(v) => (v.length > 12 ? `${v.slice(0, 11)}…` : v)}
          />
          <YAxis tick={{ fill: 'var(--text3)', fontSize: 10 }} tickFormatter={(v) => formatChartAxis(v, currency)} />
          <Tooltip
            contentStyle={chartTooltipStyle()}
            formatter={(value) => [formatCurrency(value, { currency }), fieldLabel]}
          />
          <Bar dataKey="cost" radius={[6, 6, 0, 0]} maxBarSize={48}>
            {data.map((row, i) => {
              const pct = maxCost > 0 ? (row.cost / maxCost) * 100 : 0;
              return <Cell key={row.name} fill={colors?.[i % colors.length] || barColorByPct(pct)} />;
            })}
          </Bar>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
