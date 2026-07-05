import React, { useMemo } from 'react';
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts';

const SEVERITY_Y = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1, INFO: 0 };
const CATEGORY_COLORS = {
  COMPUTE: 'var(--primary)',
  STORAGE: 'var(--info)',
  NETWORK: 'var(--purple)',
  DATABASE: 'var(--accent)',
  CONTAINERS: 'var(--success)',
  SECURITY: 'var(--danger)',
  GOVERNANCE: 'var(--warning)',
};

function severityRank(severity) {
  return SEVERITY_Y[String(severity || '').toUpperCase()] ?? 1;
}

function categoryColor(category) {
  const key = String(category || '').toUpperCase();
  return CATEGORY_COLORS[key] || 'var(--text3)';
}

export default function RecommendationsBubbleChart({ findings = [], currency = 'CAD', onSelect }) {
  const points = useMemo(() => findings.map((f) => ({
    id: f.id,
    name: f.rule_name || f.resource_name,
    category: f.category,
    savings: Number(f.estimated_savings_usd) || 0,
    severity: severityRank(f.severity),
    severityLabel: f.severity,
    z: Math.max(40, Math.min(400, (Number(f.estimated_savings_usd) || 0) * 2 + 60)),
    finding: f,
  })).filter((p) => p.savings > 0 || p.severity >= 2), [findings]);

  if (!points.length) {
    return (
      <p className="text-muted rec-bubble-empty">
        No savings-weighted recommendations to chart. Try the list or severity view.
      </p>
    );
  }

  return (
    <div className="rec-bubble-chart card chart-slot chart-slot--tall">
      <p className="rec-bubble-chart__hint text-muted text-sm">
        Bubble size reflects estimated monthly savings ({currency}). Height reflects severity.
      </p>
      <ResponsiveContainer width="100%" height={360}>
        <ScatterChart margin={{ top: 16, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" />
          <XAxis
            type="number"
            dataKey="savings"
            name="Savings"
            tick={{ fontSize: 11 }}
            label={{ value: `Est. savings/mo (${currency})`, position: 'insideBottom', offset: -4, fontSize: 11 }}
          />
          <YAxis
            type="number"
            dataKey="severity"
            name="Severity"
            domain={[0, 4.5]}
            ticks={[1, 2, 3, 4]}
            tickFormatter={(v) => ({ 1: 'Low', 2: 'Med', 3: 'High', 4: 'Critical' }[v] || '')}
            tick={{ fontSize: 11 }}
          />
          <ZAxis type="number" dataKey="z" range={[80, 400]} />
          <Tooltip
            cursor={{ strokeDasharray: '3 3' }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload;
              return (
                <div className="rec-bubble-tooltip">
                  <strong>{p.name}</strong>
                  <div>{p.severityLabel} · {p.category}</div>
                  <div>{currency} {p.savings.toLocaleString()}/mo</div>
                </div>
              );
            }}
          />
          {Object.keys(CATEGORY_COLORS).map((cat) => {
            const data = points.filter((p) => String(p.category).toUpperCase() === cat);
            if (!data.length) return null;
            return (
              <Scatter
                key={cat}
                name={cat}
                data={data}
                fill={categoryColor(cat)}
                onClick={(entry) => onSelect?.(entry?.finding)}
              />
            );
          })}
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
