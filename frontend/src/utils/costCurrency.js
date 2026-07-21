/** Azure Cost Management — billing currency (PreTaxCost) helpers. */

export const DISPLAY_CURRENCY = 'CAD';

/** Billing currency for UI — Azure Cost Management PreTaxCost is in this currency (e.g. CAD). */
export function resolveBillingCurrency(value) {
  return value || DISPLAY_CURRENCY;
}

/** MTD spend for dashboard widgets — aligns summary, sync status, and billing fields. */
export function resolveDashboardMtdAmount(costSummary, syncCost) {
  const summary = costSummary || {};
  const sync = syncCost || {};
  const pretax = Number(summary.pretax_total ?? summary.total_billing);
  if (Number.isFinite(pretax) && pretax > 0) return pretax;
  const usd = Number(summary.cost_usd_total ?? sync.total_usd);
  if (Number.isFinite(usd) && usd > 0) return usd;
  const syncBilling = Number(sync.total_billing);
  if (Number.isFinite(syncBilling) && syncBilling > 0) return syncBilling;
  return 0;
}

/** Billing currency for dashboard widgets. */
export function resolveDashboardBillingCurrency(costSummary, syncCost, fallback = DISPLAY_CURRENCY) {
  return (
    costSummary?.billing_currency
    || syncCost?.billing_currency
    || fallback
  );
}

export function billingAmount(row) {
  const billing = Number(row?.billing ?? row?.PreTaxCost ?? 0);
  return Number.isFinite(billing) ? billing : 0;
}

/** Canonical nested cost block from API row. */
export function resourceCostBlock(row) {
  if (row?.cost && typeof row.cost === 'object') {
    return row.cost;
  }
  return null;
}

/** Billed MTD in billing currency from flat or nested cost fields. */
export function resourceBilledMtd(row) {
  const block = resourceCostBlock(row);
  const fromBlock = Number(block?.billed_mtd);
  if (Number.isFinite(fromBlock) && fromBlock > 0) return fromBlock;
  return resourceMonthlyCost(row);
}

/** Azure retail / catalog monthly estimate. */
export function resourceRetailMonthly(row) {
  const block = resourceCostBlock(row);
  const fromBlock = Number(block?.retail_monthly);
  if (Number.isFinite(fromBlock) && fromBlock > 0) return fromBlock;
  const flat = Number(row?.retailMonthly ?? row?.retail_monthly);
  return Number.isFinite(flat) && flat > 0 ? flat : 0;
}

/** Currency for retail estimate display. */
export function resourceRetailCurrency(row, fallback = DISPLAY_CURRENCY) {
  const block = resourceCostBlock(row);
  return block?.retail_currency
    || row?.retailCurrency
    || row?.retail_currency
    || row?.billingCurrency
    || row?.billing_currency
    || fallback;
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
  const monthly = resourceBilledMtd(row);
  const total = row?.totalCostBilling ?? row?.total_cost_billing;
  const t = Number(total);
  if (Number.isFinite(t) && t > 0) {
    return t;
  }
  return monthly;
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
