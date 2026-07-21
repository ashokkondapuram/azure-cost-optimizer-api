import {
  unifiedResourceSavingsFromFindings,
  subscriptionUnifiedSavings,
  resolveUnifiedResourceSavings,
  sumUnifiedSavingsForFindings,
} from './unifiedSavings';

describe('unifiedSavings', () => {
  test('decommission supersedes rightsize on same resource', () => {
    const savings = unifiedResourceSavingsFromFindings([
      { rule_id: 'VM_IDLE', estimated_savings_usd: 200, status: 'open' },
      { rule_id: 'VM_OVERSIZE', estimated_savings_usd: 80, status: 'open' },
    ]);
    expect(savings).toBe(200);
  });

  test('takes max savings within same action class', () => {
    const savings = unifiedResourceSavingsFromFindings([
      { rule_id: 'DISK_UNATTACHED', estimated_savings_usd: 40, status: 'open' },
      { rule_id: 'SNAPSHOT_STALE_EXTENDED', estimated_savings_usd: 25, status: 'open' },
    ]);
    expect(savings).toBe(40);
  });

  test('subscriptionUnifiedSavings prefers unified_savings block', () => {
    expect(subscriptionUnifiedSavings({
      total_estimated_savings_usd: 999,
      unified_savings: { unified_estimated_monthly_savings: 120 },
    })).toBe(120);
  });

  test('sumUnifiedSavingsForFindings dedupes across resources', () => {
    const total = sumUnifiedSavingsForFindings([
      {
        resource_id: '/subscriptions/s/rg/providers/microsoft.compute/virtualmachines/vm1',
        rule_id: 'VM_IDLE',
        estimated_savings_usd: 200,
        status: 'open',
      },
      {
        resource_id: '/subscriptions/s/rg/providers/microsoft.compute/virtualmachines/vm1',
        rule_id: 'VM_OVERSIZE',
        estimated_savings_usd: 80,
        status: 'open',
      },
      {
        resource_id: '/subscriptions/s/rg/providers/microsoft.compute/disks/d1',
        rule_id: 'DISK_UNATTACHED',
        estimated_savings_usd: 40,
        status: 'open',
      },
    ]);
    expect(total).toBe(240);
  });

  test('resolveUnifiedResourceSavings uses savings map first', () => {
    const map = new Map([['/subscriptions/s/rg/providers/microsoft.compute/virtualmachines/vm1', 55]]);
    const amount = resolveUnifiedResourceSavings({
      resourceId: '/subscriptions/s/rg/providers/Microsoft.Compute/virtualMachines/vm1',
      findings: [{ estimated_savings_usd: 200 }],
      savingsByResource: map,
      indexReady: true,
    });
    expect(amount).toBe(55);
  });
});
