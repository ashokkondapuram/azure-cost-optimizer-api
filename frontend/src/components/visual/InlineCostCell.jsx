import React, { useMemo } from 'react';
import { formatCurrency } from '../../utils/format';
import { resourceCostTrend } from '../../utils/costCurrency';
import TrendBadge from './TrendBadge';
import MiniSparkline from './MiniSparkline';

/** Cost amount with optional trend badge and sparkline for table cells. */
export default function InlineCostCell({ amount, row, currency = 'CAD' }) {
  const cost = Number(amount) || 0;
  const trend = row ? resourceCostTrend(row) : null;

  const sparkData = useMemo(() => {
    if (cost <= 0) return null;
    const prev = trend != null ? Math.max(0, cost - trend) : cost * 0.92;
    return [{ cost: prev }, { cost }];
  }, [cost, trend]);

  if (cost <= 0) return <span className="resource-table__empty">—</span>;

  return (
    <span className="inline-cost-cell">
      <span className="inline-cost-cell__amount">{formatCurrency(cost, { currency })}</span>
      {trend != null && (
        <TrendBadge deltaAmount={trend} currency={currency} invert />
      )}
      {sparkData && <MiniSparkline data={sparkData} dataKey="cost" />}
    </span>
  );
}
