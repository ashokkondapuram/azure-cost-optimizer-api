import React from 'react';
import { formatCurrency } from '../utils/format';
import Badge from './Badge';

function resolveCostTone(amount) {
  if (amount > 800) return 'danger';
  if (amount > 300) return 'warning';
  return 'success';
}

export default function CostBadge({ value, currency = 'CAD' }) {
  const amount = Number(value);
  const tone = resolveCostTone(amount);

  return (
    <Badge tone={tone} className="tabular-nums">
      {formatCurrency(amount, { currency, decimals: 0 })}
    </Badge>
  );
}
