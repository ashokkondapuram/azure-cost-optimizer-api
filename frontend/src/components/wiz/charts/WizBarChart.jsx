import React, { useId, useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip, Cell,
} from 'recharts';
import WizChartTooltip from './WizChartTooltip';
import { CHART_PALETTE } from './wizChartColors';
import { formatCurrency } from '../../../utils/format';

export default function WizBarChart({
  title = 'Breakdown',
  subtitle,
  data = [],
  dataKey = 'value',
  nameKey = 'name',
  height = 220,
  layout = 'vertical',
  currency,
  activeName,
  onSelect,
  valueMode = 'count',
  showGrid = true,
  keepZeroValues = false,
}) {
  const uid = useId().replace(/:/g, '');
  const rows = useMemo(() => (
    [...data]
      .filter((d) => keepZeroValues || (d[dataKey] ?? d.value ?? d.count ?? 0) > 0)
      .map((d) => ({
        ...d,
        name: d[nameKey] || d.name,
        value: d[dataKey] ?? d.value ?? d.count ?? 0,
      }))
      .sort((a, b) => b.value - a.value)
  ), [data, dataKey, nameKey, keepZeroValues]);

  if (!rows.length) {
    return (
      <div className="wiz-chart-card wiz-chart-card--empty">
        <div className="wiz-chart-card__title">{title}</div>
        <p className="text-muted text-sm">No data to chart yet.</p>
      </div>
    );
  }

  return (
    <div className="wiz-chart-card">
      <div className="wiz-chart-card__head">
        <div>
          <h3 className="wiz-chart-card__title">{title}</h3>
          {subtitle && <p className="wiz-chart-card__sub">{subtitle}</p>}
        </div>
      </div>
      <div className="wiz-chart-body">
        <ResponsiveContainer width="100%" height={height}>
          <BarChart
            data={rows}
            layout={layout}
            margin={{ top: 8, right: 12, bottom: 4, left: layout === 'vertical' ? 4 : 0 }}
            onClick={(state) => {
              const name = state?.activePayload?.[0]?.payload?.name;
              if (name && onSelect) onSelect(name);
            }}
          >
            <defs>
              {rows.map((_, i) => (
                <linearGradient key={i} id={`${uid}-bar-${i}`} x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor={CHART_PALETTE[i % CHART_PALETTE.length]} stopOpacity={0.75} />
                  <stop offset="100%" stopColor={CHART_PALETTE[i % CHART_PALETTE.length]} />
                </linearGradient>
              ))}
            </defs>
            {showGrid && <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />}
            {layout === 'vertical' ? (
              <>
                <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--text3)' }} axisLine={false} tickLine={false} />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={108}
                  tick={{ fontSize: 11, fill: 'var(--text2)' }}
                  axisLine={false}
                  tickLine={false}
                />
              </>
            ) : (
              <>
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 10, fill: 'var(--text2)' }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis tick={{ fontSize: 10, fill: 'var(--text3)' }} axisLine={false} tickLine={false} />
              </>
            )}
            <Tooltip
              cursor={{ fill: 'transparent' }}
              content={(
                <WizChartTooltip
                  currency={valueMode === 'currency' ? currency : undefined}
                  valueFormatter={valueMode === 'currency'
                    ? (v) => formatCurrency(v, { currency, decimals: 0 })
                    : undefined}
                />
              )}
            />
            <Bar dataKey="value" radius={[0, 6, 6, 0]} maxBarSize={24}>
              {rows.map((row, i) => (
                <Cell
                  key={row.name}
                  fill={`url(#${uid}-bar-${i})`}
                  opacity={activeName && activeName !== row.name ? 0.4 : 1}
                  style={{ cursor: onSelect ? 'pointer' : 'default' }}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
