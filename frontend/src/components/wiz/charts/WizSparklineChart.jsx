import React, { useMemo } from 'react';
import {
  AreaChart, Area, ResponsiveContainer, Tooltip,
} from 'recharts';
import WizChartTooltip from './WizChartTooltip';

export default function WizSparklineChart({
  metricsData,
  title = 'Utilization trend',
  height = 120,
  stroke = '#0073ff',
}) {
  const points = useMemo(() => {
    const derived = metricsData?.derived || [];
    const metrics = metricsData?.metrics || [];
    const source = derived.length ? derived : metrics;
    return source.slice(0, 8).map((m, i) => ({
      name: m.label || m.name || m.id || `M${i + 1}`,
      value: Number(m.avg ?? m.value ?? m.latest ?? 0),
    })).filter((p) => p.value > 0);
  }, [metricsData]);

  if (points.length < 2) return null;

  const fillId = `wizSparkFill-${stroke.replace('#', '')}`;

  return (
    <div className="wiz-chart-card wiz-chart-card--spark">
      <h4 className="wiz-chart-card__title">{title}</h4>
      <div className="wiz-chart-body">
        <ResponsiveContainer width="100%" height={height}>
          <AreaChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
                <stop offset="100%" stopColor={stroke} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <Tooltip content={<WizChartTooltip />} />
            <Area
              type="monotone"
              dataKey="value"
              stroke={stroke}
              strokeWidth={2}
              fill={`url(#${fillId})`}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
