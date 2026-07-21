import { resourceMonthlyCost, resourceTotalCost, resourceBilledMtd, resourceRetailMonthly, resolveDashboardMtdAmount, resolveDashboardBillingCurrency } from './costCurrency';

describe('costCurrency', () => {
  it('prefers billing MTD over USD', () => {
    expect(resourceMonthlyCost({ monthlyCostBilling: 88.5, monthlyCostUsd: 0 })).toBe(88.5);
  });

  it('falls back to monthly cost when lifetime total is zero', () => {
    expect(resourceTotalCost({
      monthlyCostBilling: 42,
      totalCostBilling: 0,
    })).toBe(42);
  });

  it('uses positive lifetime total when present', () => {
    expect(resourceTotalCost({
      monthlyCostBilling: 8,
      totalCostBilling: 120,
    })).toBe(120);
  });

  it('resolves dashboard MTD from pretax_total, total_billing, and sync fallbacks', () => {
    expect(resolveDashboardMtdAmount({ pretax_total: 1200 }, null)).toBe(1200);
    expect(resolveDashboardMtdAmount({ total_billing: 900 }, null)).toBe(900);
    expect(resolveDashboardMtdAmount({}, { total_billing: 450 })).toBe(450);
    expect(resolveDashboardMtdAmount({}, { total_usd: 300 })).toBe(300);
  });

  it('resolves dashboard billing currency from summary or sync', () => {
    expect(resolveDashboardBillingCurrency({ billing_currency: 'EUR' }, null)).toBe('EUR');
    expect(resolveDashboardBillingCurrency({}, { billing_currency: 'USD' })).toBe('USD');
  });

    it('reads billed MTD and retail from nested cost block', () => {
    const row = {
      cost: {
        billed_mtd: 88.5,
        billed_currency: 'CAD',
        retail_monthly: 120,
        retail_currency: 'USD',
      },
    };
    expect(resourceBilledMtd(row)).toBe(88.5);
    expect(resourceRetailMonthly(row)).toBe(120);
  });

  it('falls back to flat billing when nested billed_mtd is zero', () => {
    expect(resourceBilledMtd({
      monthlyCostBilling: 42.5,
      cost: { billed_mtd: 0, cost_pending: true },
    })).toBe(42.5);
  });
});
