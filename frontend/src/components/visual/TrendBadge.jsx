import React from 'react';
import { TrendingDown, TrendingUp } from 'lucide-react';
import { formatCurrency } from '../../utils/format';

/** Cost trend: down is good (green), up is bad (red). Supports % or absolute billing delta. */
export default function TrendBadge({
  deltaPct,
  deltaAmount,
  currency = 'CAD',
  invert = false,
}) {
  if (deltaAmount != null && !Number.isNaN(Number(deltaAmount)) && Number(deltaAmount) !== 0) {
    const n = Number(deltaAmount);
    const up = n > 0;
    const good = invert ? up : !up;
    const mod = good ? 'down' : 'up';
    const sign = up ? '+' : '−';
    return (
      <span className={`trend-badge trend-badge--${mod}`} title="Change vs last month">
        {up ? <TrendingUp size={11} aria-hidden /> : <TrendingDown size={11} aria-hidden />}
        {sign}{formatCurrency(Math.abs(n), { currency, decimals: 0 })}
      </span>
    );
  }

  if (deltaPct == null || Number.isNaN(deltaPct)) return null;
  const n = Number(deltaPct);
  const up = n > 0;
  const good = invert ? up : !up;
  const mod = good ? 'down' : 'up';
  return (
    <span className={`trend-badge trend-badge--${mod}`}>
      {up ? <TrendingUp size={11} aria-hidden /> : <TrendingDown size={11} aria-hidden />}
      {Math.abs(n).toFixed(1)}%
    </span>
  );
}
