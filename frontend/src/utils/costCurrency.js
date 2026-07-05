/** Azure Cost Management — billing currency (PreTaxCost) helpers. */

export const DISPLAY_CURRENCY = 'CAD';

/** Billing currency for UI — Azure Cost Management PreTaxCost is in this currency (e.g. CAD). */
export function resolveBillingCurrency(value) {
  return value || DISPLAY_CURRENCY;
}

export function billingAmount(row) {
  const billing = Number(row?.billing ?? row?.PreTaxCost ?? 0);
  return Number.isFinite(billing) ? billing : 0;
}

/** MTD cost on a resource row (billing currency preferred, then USD). */
export function resourceMonthlyCost(row) {
  const billing = row?.monthlyCostBilling ?? row?.monthly_cost_billing;
  const usd = row?.monthlyCostUsd ?? row?.monthly_cost_usd;
  const b = Number(billing);
  const u = Number(usd);
  if (Number.isFinite(b) && b > 0) return b;
  if (Number.isFinite(u) && u > 0) return u;
  return 0;
}

/** Cumulative billed cost across synced months (falls back to MTD when absent). */
export function resourceTotalCost(row) {
  const total = row?.totalCostBilling ?? row?.total_cost_billing;
  const t = Number(total);
  if (Number.isFinite(t) && t >= 0 && (t > 0 || row?.totalCostBilling != null || row?.total_cost_billing != null)) {
    return t;
  }
  return resourceMonthlyCost(row);
}

/** Month-over-month billing change for trend display. */
export function resourceCostTrend(row) {
  const delta = row?.costTrendBilling ?? row?.cost_trend_billing;
  const n = Number(delta);
  return Number.isFinite(n) ? n : null;
}

export function azureFieldLabel(billingCurrency = 'CAD') {
  return `PreTaxCost (${billingCurrency})`;
}

export function formatChartAxis(value, currency = DISPLAY_CURRENCY) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '';
  const sym = currency === 'CAD' ? 'CA$' : '$';
  if (Math.abs(n) >= 1_000_000) return `${sym}${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `${sym}${(n / 1_000).toFixed(0)}k`;
  return `${sym}${Math.round(n)}`;
}
