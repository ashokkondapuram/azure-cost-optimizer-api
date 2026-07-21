import React, { useMemo } from 'react';
import { formatIsoCurrency } from '../../utils/costExplorerV2Utils';

export default function CostExplorerBudgetStrip({
  budgets,
  currency,
  currentSpend,
  projectedMonthEnd,
  daysRemaining,
  avgDaily,
}) {
  const budget = useMemo(() => {
    if (!budgets?.length) return null;
    const monthly = budgets.find((b) => (b.timeGrain || b.time_grain || '').toLowerCase().includes('month'))
      || budgets[0];
    const amount = Number(monthly.amount ?? monthly.budget_amount ?? 0);
    if (!amount) return null;
    return {
      name: monthly.name || monthly.budget_name || 'Monthly budget',
      amount,
      currentSpend: Number(monthly.currentSpend ?? monthly.current_spend ?? currentSpend ?? 0),
    };
  }, [budgets, currentSpend]);

  if (!budget) return null;

  const consumedPct = Math.min(100, Math.round((budget.currentSpend / budget.amount) * 100));
  const projected = projectedMonthEnd ?? budget.currentSpend;
  const overAmount = projected - budget.amount;
  const atRisk = overAmount > 0 || consumedPct >= 85;
  const pillClass = atRisk ? 'ce-budget-pill--warn' : 'ce-budget-pill--ok';
  const pillLabel = atRisk ? 'At risk' : 'On track';

  return (
    <div className="ce-budget-strip" aria-label="Monthly budget">
      <div className="ce-budget-strip__copy">
        <span className="ce-budget-strip__label">{budget.name}</span>
        <strong className="ce-budget-strip__amount">
          {formatIsoCurrency(budget.amount, currency, { decimals: 0 })}
        </strong>
        <span className="ce-budget-strip__hint">
          {consumedPct}% consumed
          {avgDaily ? ` · Burn rate ${formatIsoCurrency(avgDaily, currency, { decimals: 0 })}/day` : ''}
          {daysRemaining != null ? ` · ${daysRemaining} days remaining` : ''}
        </span>
      </div>
      <div className="ce-budget-strip__meter">
        <div className="ce-budget-strip__fill" id="ce-budget-fill" style={{ width: `${consumedPct}%` }} />
        <span
          className="ce-budget-strip__marker"
          id="ce-budget-marker"
          style={{ left: `${consumedPct}%` }}
          aria-hidden="true"
        />
      </div>
      <div className="ce-budget-strip__status">
        <span className={`ce-budget-pill ${pillClass}`}>{pillLabel}</span>
        <span className="ce-budget-strip__forecast">
          {projectedMonthEnd != null && (
            <>
              Projected month-end {formatIsoCurrency(projectedMonthEnd, currency, { decimals: 0 })}
              {overAmount > 0 && (
                <> · Est. {formatIsoCurrency(overAmount, currency, { decimals: 0 })} over budget</>
              )}
            </>
          )}
        </span>
      </div>
    </div>
  );
}
