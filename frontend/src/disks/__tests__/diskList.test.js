import {
  diskMatchesFilters,
  sortConceptDisks,
  diskTableColumns,
  formatDiskMetric,
} from '../diskList';
import { DISK_LIST_COLUMNS } from '../diskAssessment';

describe('diskList', () => {
  const sample = {
    name: 'disk-01',
    resourceGroup: 'rg-apps',
    region: 'Canada Central',
    properties: { diskState: 'Unattached', sku: 'Premium_LRS' },
    cost: { billed_mtd: 10, retail_monthly: 42 },
    finding: { rule_id: 'DISK_UNUSED_EXTENDED', severity: 'high' },
    metrics: { disk_iops_utilization_pct: 5 },
  };

  test('diskMatchesFilters respects chip filters', () => {
    expect(diskMatchesFilters(sample, { chip: 'unattached' })).toBe(true);
    expect(diskMatchesFilters(sample, { chip: 'attached' })).toBe(false);
    expect(diskMatchesFilters(sample, { chip: 'finding' })).toBe(true);
    expect(diskMatchesFilters({ ...sample, finding: null }, { chip: 'finding' })).toBe(false);
  });

  test('sortConceptDisks sorts by billed_mtd', () => {
    const rows = [
      { ...sample, name: 'a', cost: { billed_mtd: 5 } },
      { ...sample, name: 'b', cost: { billed_mtd: 20 } },
    ];
    const sorted = sortConceptDisks(rows, 'billed_mtd', 'desc');
    expect(sorted[0].name).toBe('b');
  });

  test('diskTableColumns includes assessment columns', () => {
    const cols = diskTableColumns();
    expect(cols[0]).toEqual({ key: 'name', label: 'Disk' });
    expect(cols.some((c) => c.key === DISK_LIST_COLUMNS[0].key)).toBe(true);
    expect(cols.some((c) => c.key === 'billed_mtd')).toBe(true);
  });

  test('formatDiskMetric formats percent', () => {
    expect(formatDiskMetric(12, '%')).toBe('12%');
    expect(formatDiskMetric(null, '%')).toBe('—');
  });
});
