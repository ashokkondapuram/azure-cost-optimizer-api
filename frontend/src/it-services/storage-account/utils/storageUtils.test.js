import {
  formatAccessTier,
  formatReplicationSku,
  formatStorageMetric,
  MISSING_DISPLAY,
} from './storageUtils';

describe('storageUtils', () => {
  it('distinguishes missing from zero for metrics', () => {
    expect(formatStorageMetric('transaction_count', null)).toBe(MISSING_DISPLAY);
    expect(formatStorageMetric('transaction_count', 0)).toBe('0 transactions');
    expect(formatStorageMetric('used_capacity_bytes', 0)).toBe('0 GB used');
  });

  it('formats replication SKU for humans', () => {
    expect(formatReplicationSku('STANDARD_GRS')).toMatch(/geo-redundant/i);
  });

  it('formats access tier labels', () => {
    expect(formatAccessTier('Cool')).toBe('Cool');
    expect(formatAccessTier(null)).toBe('—');
  });
});
