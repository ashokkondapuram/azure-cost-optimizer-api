import React from 'react';

/**
 * Compact horizontal utilization gauge for table cells.
 */
export default function InlineGauge({
  value,
  max = 100,
  label,
  tone = 'default',
}) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  const pct = Math.max(0, Math.min(100, (numeric / max) * 100));
  const resolvedTone = tone === 'default'
    ? (pct >= 85 ? 'high' : pct >= 60 ? 'medium' : 'low')
    : tone;

  return (
    <span className={`inline-gauge inline-gauge--${resolvedTone}`} title={label || `${Math.round(pct)}%`}>
      <span className="inline-gauge__track" aria-hidden>
        <span className="inline-gauge__fill" style={{ width: `${pct}%` }} />
      </span>
      <span className="inline-gauge__value">{Math.round(numeric)}%</span>
    </span>
  );
}
