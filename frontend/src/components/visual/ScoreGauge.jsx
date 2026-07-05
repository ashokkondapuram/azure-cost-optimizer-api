import React from 'react';

export default function ScoreGauge({ label, value, max = 100 }) {
  if (value == null || value === '') return null;
  const n = Math.max(0, Math.min(max, Number(value) || 0));
  const pct = max ? (n / max) * 100 : 0;
  const hue = Math.round(pct * 1.2);
  return (
    <div className="score-gauge">
      <span className="score-gauge__label">{label}</span>
      <div className="score-gauge__track">
        <div
          className="score-gauge__fill"
          style={{ width: `${pct}%`, background: `hsl(${hue}, 70%, 45%)` }}
        />
      </div>
      <span className="score-gauge__value">{n}{max === 100 ? '%' : ''}</span>
    </div>
  );
}
