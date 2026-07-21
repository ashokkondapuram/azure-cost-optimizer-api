import React, { useMemo } from 'react';
import { formatIsoCurrency } from '../../utils/costExplorerV2Utils';

const METER_COLORS = ['#60a5fa', '#f87171', '#a78bfa', '#34d399', '#94a3b8'];

export default function CostExplorerAllocation({
  total,
  amortizedTotal,
  currency,
  serviceRows,
}) {
  const unblended = total;
  const amortized = amortizedTotal ?? null;
  const meterRows = useMemo(() => {
    const max = Math.max(...(serviceRows || []).map((r) => r.cost), 1);
    return (serviceRows || []).slice(0, 5).map((row, i) => ({
      ...row,
      widthPct: Math.round((row.cost / max) * 100),
      color: METER_COLORS[i % METER_COLORS.length],
    }));
  }, [serviceRows]);

  return (
    <div className="panel ce-allocation-panel">
      <div className="panel-head panel-head--inset">
        <h2 className="section-title section-title--bar">Service allocation</h2>
      </div>
      <div className="ce-allocation-body">
        <div className="ce-allocation-split">
          <div className="ce-allocation-metric">
            <span className="ce-allocation-metric__label">Amortized cost</span>
            <strong className="ce-allocation-metric__value">
              {amortized != null
                ? formatIsoCurrency(amortized, currency, { decimals: 0 })
                : '—'}
            </strong>
            <span className="ce-allocation-metric__sub">
              {amortized != null && total > 0
                ? `${((amortized / total) * 100).toFixed(1)}% of period total`
                : 'Amortized cost not available from synced data'}
            </span>
          </div>
          <div className="ce-allocation-metric">
            <span className="ce-allocation-metric__label">Unblended cost</span>
            <strong className="ce-allocation-metric__value">
              {formatIsoCurrency(unblended, currency, { decimals: 0 })}
            </strong>
            <span className="ce-allocation-metric__sub">Billed amount for selected period</span>
          </div>
        </div>
        <h3 className="ce-allocation-subtitle">By meter category</h3>
        {meterRows.length === 0 ? (
          <p className="panel-empty">No service allocation data.</p>
        ) : (
          <div className="category-chart category-chart--compact ce-allocation-chart">
            {meterRows.map((row) => (
              <div key={row.key} className="category-row">
                <span className="category-label">
                  <span className="cat-dot" style={{ '--cat-color': row.color }} />
                  {row.name}
                </span>
                <div className="category-track">
                  <div
                    className="category-fill"
                    style={{ width: `${row.widthPct}%`, '--cat-color': row.color }}
                  />
                </div>
                <span className="category-count" data-currency={currency}>
                  {formatIsoCurrency(row.cost, currency, { decimals: 0 }).replace(`${currency} `, '')}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
