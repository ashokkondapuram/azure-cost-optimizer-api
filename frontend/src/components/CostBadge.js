import React from 'react';
import { formatCurrency } from '../utils/format';

export default function CostBadge({ value, currency = 'CAD' }) {
  const amount = Number(value);
  const color = amount > 800 ? '#c0392b' : amount > 300 ? '#d67f00' : '#107c10';
  const bg = amount > 800 ? '#fde7e9' : amount > 300 ? '#fff4ce' : '#dff6dd';
  return (
    <span style={{
      fontWeight: 700,
      color,
      background: bg,
      padding: '3px 9px',
      borderRadius: 6,
      fontSize: '0.82rem',
    }}>
      {formatCurrency(amount, { currency, decimals: 0 })}
    </span>
  );
}
