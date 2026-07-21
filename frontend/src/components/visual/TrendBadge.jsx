import React from 'react';
import { TrendingDown, TrendingUp } from 'lucide-react';
import { formatCurrency } from '../../utils/format';
import Badge from '../Badge';

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
    const tone = good ? 'success' : 'danger';
    const sign = up ? '+' : '−';
    return (
      <Badge
        tone={tone}
        icon={up ? <TrendingUp size={11} aria-hidden /> : <TrendingDown size={11} aria-hidden />}
        title="Change vs last month"
      >
        {sign}{formatCurrency(Math.abs(n), { currency, decimals: 0 })}
      </Badge>
    );
  }

  if (deltaPct == null || Number.isNaN(deltaPct)) return null;
  const n = Number(deltaPct);
  const up = n > 0;
  const good = invert ? up : !up;
  const tone = good ? 'success' : 'danger';
  return (
    <Badge
      tone={tone}
      icon={up ? <TrendingUp size={11} aria-hidden /> : <TrendingDown size={11} aria-hidden />}
    >
      {Math.abs(n).toFixed(1)}%
    </Badge>
  );
}
