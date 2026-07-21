import {
  groupFindingsBySeverity,
  summarizeBySeverity,
  findingAffectedLabel,
  formatCategoryLabel,
} from './recommendationGrouping';

describe('recommendationGrouping', () => {
  const findings = [
    { id: '1', severity: 'HIGH', estimated_savings_usd: 50, rule_name: 'A', category: 'COMPUTE' },
    { id: '2', severity: 'CRITICAL', estimated_savings_usd: 100, rule_name: 'B', category: 'NETWORK' },
    { id: '3', severity: 'CRITICAL', estimated_savings_usd: 200, rule_name: 'C', category: 'COMPUTE' },
  ];

  it('groups by severity in priority order', () => {
    const groups = groupFindingsBySeverity(findings);
    expect(groups.map((g) => g.severity)).toEqual(['CRITICAL', 'HIGH']);
    expect(groups[0].findings).toHaveLength(2);
    expect(groups[0].findings[0].id).toBe('3');
  });

  it('summarizes totals', () => {
    const { totalCount, totalSavings } = summarizeBySeverity(findings);
    expect(totalCount).toBe(3);
    expect(totalSavings).toBe(350);
  });

  it('formats affected resource label', () => {
    expect(findingAffectedLabel({ resource_name: 'vm-1' })).toBe('1 resource · vm-1');
    expect(findingAffectedLabel({})).toBe('Subscription');
  });

  it('formats category labels in sentence case', () => {
    expect(formatCategoryLabel('COMPUTE')).toBe('Compute');
    expect(formatCategoryLabel('kubernetes')).toBe('Kubernetes');
  });
});
