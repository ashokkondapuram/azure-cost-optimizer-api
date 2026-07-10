import React, { useMemo, memo } from 'react';
import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { tierLabel, tierTone } from '../../utils/scoreboardUtils';

const TIER_COLORS = {
  tier1_safe: 'var(--success)',
  tier2_balanced: 'var(--primary)',
  tier3_risky: 'var(--warning)',
  blocked: 'var(--danger)',
  maintenance_hold: 'var(--text3)',
};

const SCORE_BUCKETS = [
  { label: '0–20', min: 0, max: 20 },
  { label: '20–40', min: 20, max: 40 },
  { label: '40–60', min: 40, max: 60 },
  { label: '60–80', min: 60, max: 80 },
  { label: '80–100', min: 80, max: 101 },
];

function buildTierData(items, tierSummary) {
  const counts = {
    tier1_safe: tierSummary?.tier1_safe || 0,
    tier2_balanced: tierSummary?.tier2_balanced || 0,
    tier3_risky: tierSummary?.tier3_risky || 0,
    blocked: tierSummary?.blocked || 0,
  };
  if (!Object.values(counts).some((v) => v > 0)) {
    for (const row of items) {
      const t = row.recommendation_tier;
      if (t && counts[t] != null) counts[t] += 1;
    }
  }
  return Object.entries(counts)
    .filter(([, value]) => value > 0)
    .map(([tier, value]) => ({
      tier,
      name: tierLabel(tier),
      value,
      tone: tierTone(tier),
    }));
}

function buildHistogram(items) {
  const buckets = SCORE_BUCKETS.map((b) => ({ ...b, count: 0 }));
  for (const row of items) {
    const score = Number(row.overall_recommendation_score);
    if (Number.isNaN(score)) continue;
    const bucket = buckets.find((b) => score >= b.min && score < b.max);
    if (bucket) bucket.count += 1;
  }
  return buckets.map((b) => ({ name: b.label, count: b.count }));
}

function ScoreboardCharts({ items = [], tierSummary = {}, activeTier = '', onTierClick }) {
  const tierData = useMemo(() => buildTierData(items, tierSummary), [items, tierSummary]);
  const histogram = useMemo(() => buildHistogram(items), [items]);

  if (!items.length) return null;

  return (
    <section className="scoreboard-charts card chart-slot" aria-label="Score distribution charts">
      <div className="scoreboard-charts__grid">
        <div className="scoreboard-charts__panel">
          <h3 className="scoreboard-charts__title">Tier distribution</h3>
          <div className="scoreboard-charts__chart">
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={tierData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={48}
                  outerRadius={78}
                  paddingAngle={2}
                >
                  {tierData.map((entry) => (
                    <Cell key={entry.tier} fill={TIER_COLORS[entry.tier] || 'var(--text3)'} />
                  ))}
                </Pie>
                <Tooltip formatter={(value, name) => [value, name]} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <ul className="scoreboard-charts__legend">
            {tierData.map((entry) => {
              const active = activeTier === entry.tier;
              const clickable = typeof onTierClick === 'function';
              return (
                <li key={entry.tier}>
                  {clickable ? (
                    <button
                      type="button"
                      className={`scoreboard-charts__legend-btn${active ? ' scoreboard-charts__legend-btn--active' : ''}`}
                      onClick={() => onTierClick(active ? '' : entry.tier)}
                    >
                      <span className={`tier-pill tier-pill--${entry.tone}`}>{entry.name}</span>
                      <span>{entry.value}</span>
                    </button>
                  ) : (
                    <>
                      <span className={`tier-pill tier-pill--${entry.tone}`}>{entry.name}</span>
                      <span>{entry.value}</span>
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        </div>

        <div className="scoreboard-charts__panel">
          <h3 className="scoreboard-charts__title">Overall score distribution</h3>
          <div className="scoreboard-charts__chart">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={histogram} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} width={28} />
                <Tooltip />
                <Bar dataKey="count" fill="var(--primary)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </section>
  );
}

export default memo(ScoreboardCharts);
