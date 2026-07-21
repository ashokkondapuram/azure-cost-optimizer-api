import React from 'react';
import { formatCurrency } from '../../../utils/format';

export default function WizChartTooltip({
  active,
  payload,
  label,
  currency,
  valueFormatter,
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0]?.payload || {};
  const name = label || row.name || row.label || payload[0]?.name;
  const raw = payload[0]?.value ?? row.value ?? row.count;
  const value = valueFormatter
    ? valueFormatter(raw, row)
    : (typeof raw === 'number' && currency
      ? formatCurrency(raw, { currency, decimals: 0 })
      : (typeof raw === 'number'
        ? raw.toLocaleString()
        : String(raw ?? '')));

  return (
    <div className="wiz-chart-tooltip" role="tooltip">
      <div className="wiz-chart-tooltip__label">{name}</div>
      <div className="wiz-chart-tooltip__value">{value}</div>
      {row.savings != null && currency && (
        <div className="wiz-chart-tooltip__sub">
          {formatCurrency(row.savings, { currency, decimals: 0 })}
          {' '}
          savings
        </div>
      )}
    </div>
  );
}
