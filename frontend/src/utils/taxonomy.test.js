import {
  compareResourceRowsByPriority,
  formatCategoryLabel,
  groupResourceRows,
  groupRowsByResourceGroup,
  groupRowsByService,
  sortFindingsByPriority,
} from './taxonomy';

describe('taxonomy', () => {
  it('sorts findings by severity then savings', () => {
    const ordered = sortFindingsByPriority([
      { severity: 'LOW', estimated_savings_usd: 200 },
      { severity: 'CRITICAL', estimated_savings_usd: 5 },
      { severity: 'HIGH', estimated_savings_usd: 50 },
    ]);
    expect(ordered.map((f) => f.severity)).toEqual(['CRITICAL', 'HIGH', 'LOW']);
  });

  it('compares resource rows by priority', () => {
    const rows = [
      { row: { name: 'b' }, rec: { topFinding: { severity: 'LOW' }, savings: 100, findingCount: 1 } },
      { row: { name: 'a' }, rec: { topFinding: { severity: 'HIGH' }, savings: 10, findingCount: 2 } },
    ];
    const sorted = [...rows].sort(compareResourceRowsByPriority);
    expect(sorted[0].row.name).toBe('a');
  });

  it('groups rows by service with savings totals', () => {
    const groups = groupRowsByService([
      { row: { azureServiceName: 'Disks' }, rec: { savings: 20 } },
      { row: { azureServiceName: 'Virtual Machines' }, rec: { savings: 80 } },
      { row: { azureServiceName: 'Virtual Machines' }, rec: { savings: 10 } },
    ]);
    expect(groups[0].label).toBe('Virtual Machines');
    expect(groups[0].savings).toBe(90);
  });

  it('groups rows by resource group with savings totals', () => {
    const groups = groupRowsByResourceGroup([
      { row: { resourceGroup: 'rg-prod' }, rec: { savings: 30 } },
      { row: { resourceGroup: 'rg-dev' }, rec: { savings: 10 } },
      { row: { resourceGroup: 'rg-prod' }, rec: { savings: 20 } },
    ]);
    expect(groups[0].label).toBe('rg-prod');
    expect(groups[0].savings).toBe(50);
  });

  it('groupResourceRows returns null for flat list', () => {
    expect(groupResourceRows([{ row: {} }], '')).toBeNull();
    expect(groupResourceRows([{ row: {} }], 'service')).toHaveLength(1);
  });

  it('formats category labels consistently', () => {
    expect(formatCategoryLabel('COMPUTE')).toBe('Compute');
    expect(formatCategoryLabel('kubernetes')).toBe('Kubernetes');
  });
});
