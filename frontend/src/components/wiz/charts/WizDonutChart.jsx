import React, { useId, useMemo } from 'react';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
} from 'recharts';
import WizChartTooltip from './WizChartTooltip';
import {
  SEVERITY_ORDER, SEVERITY_FILL, SEVERITY_GRADIENTS, CHART_PALETTE,
} from './wizChartColors';

function normalizeSeverityKey(key) {
  return String(key || '').trim().toUpperCase();
}

function resolveGradientStops(key, index) {
  const normalized = normalizeSeverityKey(key);
  const gradient = SEVERITY_GRADIENTS[normalized];
  if (Array.isArray(gradient) && gradient.length >= 2) return gradient;
  const fill = SEVERITY_FILL[normalized];
  if (fill) return [fill, fill];
  const palette = CHART_PALETTE[index % CHART_PALETTE.length];
  if (typeof palette === 'string' && palette.startsWith('#')) {
    return [palette, palette];
  }
  return ['#6366f1', '#4f46e5'];
}

function buildGradientDefs(data, uid) {
  return (
    <defs>
      {data.map((entry, i) => {
        const key = normalizeSeverityKey(entry.key || entry.name);
        const [light, dark] = resolveGradientStops(key, i);
        return (
          <linearGradient key={`${key}-${i}`} id={`${uid}-grad-${i}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={light} />
            <stop offset="100%" stopColor={dark} />
          </linearGradient>
        );
      })}
    </defs>
  );
}

export default function WizDonutChart({
  title = 'Distribution',
  subtitle,
  data = [],
  height = 200,
  innerRadius = 52,
  outerRadius = 78,
  centerLabel,
  centerValue,
  activeKey,
  onSelect,
  currency,
  valueMode = 'count',
}) {
  const uid = useId().replace(/:/g, '');
  const chartData = useMemo(() => (
    data.filter((d) => (d.value ?? d.count ?? 0) > 0).map((d) => ({
      ...d,
      value: d.value ?? d.count ?? 0,
      name: d.name || d.label || d.key,
    }))
  ), [data]);

  if (!chartData.length) {
    return (
      <div className="wiz-chart-card wiz-chart-card--empty">
        <div className="wiz-chart-card__title">{title}</div>
        <p className="text-muted text-sm">No data to chart yet.</p>
      </div>
    );
  }

  const total = chartData.reduce((s, d) => s + d.value, 0);

  return (
    <div className="wiz-chart-card">
      <div className="wiz-chart-card__head">
        <div>
          <h3 className="wiz-chart-card__title">{title}</h3>
          {subtitle && <p className="wiz-chart-card__sub">{subtitle}</p>}
        </div>
      </div>

      <div className="wiz-chart-body wiz-chart-body--donut">
        <ResponsiveContainer width="100%" height={height}>
          <PieChart>
            {buildGradientDefs(chartData, uid)}
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={innerRadius}
              outerRadius={outerRadius}
              dataKey="value"
              paddingAngle={2}
              stroke="var(--border-subtle)"
              strokeWidth={1}
              onClick={(_, index) => onSelect?.(chartData[index])}
            >
              {chartData.map((entry, i) => {
                const key = normalizeSeverityKey(entry.key || entry.name);
                const active = activeKey && normalizeSeverityKey(activeKey) === key;
                return (
                  <Cell
                    key={`${key}-${i}`}
                    fill={`url(#${uid}-grad-${i})`}
                    opacity={activeKey && !active ? 0.45 : 1}
                    style={{ cursor: onSelect ? 'pointer' : 'default' }}
                  />
                );
              })}
            </Pie>
            <Tooltip
              cursor={{ fill: 'transparent' }}
              content={(
                <WizChartTooltip
                  currency={valueMode === 'currency' ? currency : undefined}
                  valueFormatter={valueMode === 'count'
                    ? (v) => `${v} (${Math.round((v / total) * 100)}%)`
                    : undefined}
                />
              )}
            />
          </PieChart>
        </ResponsiveContainer>
        {(centerLabel || centerValue != null) && (
          <div className="wiz-chart-body__center">
            {centerValue != null && <strong>{centerValue}</strong>}
            {centerLabel && <span>{centerLabel}</span>}
          </div>
        )}
      </div>

      <div className="wiz-chart-legend">
        {chartData.map((d, i) => {
          const key = normalizeSeverityKey(d.key || d.name);
          const color = SEVERITY_FILL[key] || SEVERITY_GRADIENTS[key]?.[1] || '#6366f1';
          return (
            <button
              key={`${key}-${i}`}
              type="button"
              className={`wiz-chart-legend__chip${normalizeSeverityKey(activeKey) === key ? ' wiz-chart-legend__chip--active' : ''}`}
              onClick={() => onSelect?.(d)}
            >
              <span className="wiz-chart-legend__dot" style={{ background: color }} />
              {d.name}
              {' '}
              <strong>{d.value.toLocaleString()}</strong>
            </button>
          );
        })}
      </div>
    </div>
  );
}

const SEVERITY_LABELS = {
  CRITICAL: 'Critical',
  HIGH: 'High',
  MEDIUM: 'Medium',
  LOW: 'Low',
  INFO: 'Info',
};

export function severityDonutData(bySeverity = {}) {
  const normalized = {};
  for (const [rawKey, rawValue] of Object.entries(bySeverity || {})) {
    const key = normalizeSeverityKey(rawKey);
    if (!key) continue;
    normalized[key] = (normalized[key] || 0) + (Number(rawValue) || 0);
  }
  return SEVERITY_ORDER.map((key) => ({
    key,
    name: SEVERITY_LABELS[key] || key,
    count: normalized[key] ?? 0,
    value: normalized[key] ?? 0,
  })).filter((d) => d.value > 0);
}

export function categoryBarData(byCategory = {}, limit = 8) {
  return Object.entries(byCategory || {})
    .map(([name, count]) => ({ name, count, value: count }))
    .sort((a, b) => b.value - a.value)
    .slice(0, limit);
}

const SOURCE_COLORS = {
  cost_performance: '#0073ff',
  reliability_security: '#f97316',
  governance: '#8b5cf6',
};

export function sourceBarData(items = []) {
  return (items || [])
    .filter((item) => Number(item.count) > 0)
    .map((item) => ({
      key: item.key,
      name: item.label || item.key,
      count: Number(item.count) || 0,
      value: Number(item.count) || 0,
      fill: SOURCE_COLORS[item.key] || '#6366f1',
    }));
}
