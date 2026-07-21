import React, { useMemo } from 'react';
import { formatCurrency } from '../../utils/format';
import {
  resourceBilledMtd,
  resourceCostTrend,
  resourceRetailCurrency,
  resourceRetailMonthly,
} from '../../utils/costCurrency';
import TrendBadge from './TrendBadge';
import MiniSparkline from './MiniSparkline';

const RETAIL_TOOLTIP = 'Catalog pricing from Azure Retail Prices — estimated monthly, not your invoice.';

/** Cost amount with billed MTD, optional retail estimate, trend badge and sparkline. */
export default function InlineCostCell({ amount, row, currency = 'CAD' }) {
  const billed = Number(amount) || resourceBilledMtd(row);
  const retail = resourceRetailMonthly(row);
  const retailCurrency = resourceRetailCurrency(row, currency);
  const trend = row ? resourceCostTrend(row) : null;

  const sparkData = useMemo(() => {
    if (billed <= 0) return null;
    const prev = trend != null ? Math.max(0, billed - trend) : billed * 0.92;
    return [{ cost: prev }, { cost: billed }];
  }, [billed, trend]);

  if (billed <= 0 && retail <= 0) {
    return <span className="resource-table__empty">—</span>;
  }

  return (
    <span className="inline-cost-cell">
      {billed > 0 && (
        <span className="inline-cost-cell__stack">
          <span className="inline-cost-cell__amount" title="Month to date (billed)">
            {formatCurrency(billed, { currency })}
          </span>
          {retail > 0 && (
            <span
              className="inline-cost-cell__retail"
              title={RETAIL_TOOLTIP}
            >
              Retail
              {' '}
              {formatCurrency(retail, { currency: retailCurrency })}
            </span>
          )}
        </span>
      )}
      {billed <= 0 && retail > 0 && (
        <span className="inline-cost-cell__retail-only" title={RETAIL_TOOLTIP}>
          Retail
          {' '}
          {formatCurrency(retail, { currency: retailCurrency })}
        </span>
      )}
      {trend != null && billed > 0 && (
        <TrendBadge deltaAmount={trend} currency={currency} invert />
      )}
      {sparkData && <MiniSparkline data={sparkData} dataKey="cost" />}
    </span>
  );
}
