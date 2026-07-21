import React, { useMemo } from 'react';
import {
  RadialBarChart, RadialBar, ResponsiveContainer, PolarAngleAxis, Tooltip,
} from 'recharts';
import WizChartTooltip from './WizChartTooltip';

export default function WizRadialGauge({
  title = 'Score',
  subtitle,
  value = 0,
  max = 100,
  label,
  fill = '#22c55e',
  height = 180,
  currency,
  formatValue,
}) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
  const data = useMemo(() => ([
    { name: label || title, value: pct, fill },
  ]), [pct, fill, label, title]);

  const display = formatValue
    ? formatValue(value)
    : (currency
      ? `${Math.round(pct)}%`
      : `${Math.round(value)}`);

  return (
    <div className="wiz-chart-card">
      <div className="wiz-chart-card__head">
        <div>
          <h3 className="wiz-chart-card__title">{title}</h3>
          {subtitle && <p className="wiz-chart-card__sub">{subtitle}</p>}
        </div>
      </div>
      <div className="wiz-chart-body wiz-chart-body--gauge">
        <ResponsiveContainer width="100%" height={height}>
          <RadialBarChart
            cx="50%"
            cy="50%"
            innerRadius="62%"
            outerRadius="88%"
            barSize={12}
            data={data}
            startAngle={220}
            endAngle={-40}
          >
            <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
            <RadialBar
              dataKey="value"
              cornerRadius={6}
              background={{ fill: 'rgba(128,128,128,0.12)' }}
            />
            <Tooltip content={<WizChartTooltip />} />
          </RadialBarChart>
        </ResponsiveContainer>
        <div className="wiz-chart-body__center wiz-chart-body__center--gauge">
          <strong>{display}</strong>
          {label && <span>{label}</span>}
        </div>
      </div>
    </div>
  );
}
