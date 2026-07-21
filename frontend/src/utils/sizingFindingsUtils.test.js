import { hasRightsizingFinding, mergeLiveVmSizingFindings } from './sizingFindingsUtils';

describe('mergeLiveVmSizingFindings', () => {
  const sizingData = {
    current_sku: 'Standard_D2ads_v6',
    recommendation: {
      action: 'downgrade',
      suggested_sku: 'Standard_B1ls',
      reasons: ['Low average CPU utilization'],
    },
    pricing: { estimated_monthly_savings_usd: 55 },
  };

  it('adds preview finding when sizing exists and none persisted', () => {
    const merged = mergeLiveVmSizingFindings([], sizingData);
    expect(merged).toHaveLength(1);
    expect(merged[0].severity).toBe('MEDIUM');
    expect(merged[0].rule_id).toBe('VM_SKU_SIZING_EXTENDED');
  });

  it('does not duplicate when rightsizing finding already exists', () => {
    const existing = [{ rule_id: 'VM_SKU_SIZING_EXTENDED', severity: 'MEDIUM' }];
    expect(mergeLiveVmSizingFindings(existing, sizingData)).toEqual(existing);
    expect(hasRightsizingFinding(existing)).toBe(true);
  });
});
