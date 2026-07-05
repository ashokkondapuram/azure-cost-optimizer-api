import {
  normalizeQuery,
  textIncludes,
  matchResourceRow,
  matchFinding,
  uniqueSorted,
  resourceGroupOf,
  uniqueResourceGroups,
  countActiveFilters,
} from './filterUtils';

describe('filterUtils', () => {
  test('normalizeQuery trims and lowercases', () => {
    expect(normalizeQuery('  Foo ')).toBe('foo');
    expect(normalizeQuery('')).toBe('');
  });

  test('textIncludes matches case-insensitively', () => {
    expect(textIncludes('Hello World', 'world')).toBe(true);
    expect(textIncludes('Hello', 'xyz')).toBe(false);
    expect(textIncludes('anything', '')).toBe(true);
  });

  test('matchResourceRow searches standard fields', () => {
    const row = {
      name: 'web-vm-01',
      resourceGroup: 'prod-rg',
      location: 'canadacentral',
    };
    expect(matchResourceRow(row, 'web-vm')).toBe(true);
    expect(matchResourceRow(row, 'prod-rg')).toBe(true);
    expect(matchResourceRow(row, 'westus')).toBe(false);
  });

  test('matchResourceRow supports extra field extractors', () => {
    const row = { name: 'disk-a' };
    expect(matchResourceRow(row, 'premium', [(r) => r.sku])).toBe(false);
    expect(matchResourceRow(row, 'premium', [() => 'Premium_LRS'])).toBe(true);
  });

  test('matchFinding searches recommendation fields', () => {
    const finding = {
      rule_name: 'Idle VM',
      resource_name: 'vm-test',
      severity: 'HIGH',
      detail: 'CPU below threshold',
    };
    expect(matchFinding(finding, 'idle')).toBe(true);
    expect(matchFinding(finding, 'vm-test')).toBe(true);
    expect(matchFinding(finding, 'xyz')).toBe(false);
  });

  test('uniqueSorted dedupes and sorts', () => {
    expect(uniqueSorted(['b', 'a', 'b', null, ''])).toEqual(['a', 'b']);
  });

  test('resourceGroupOf and uniqueResourceGroups', () => {
    const rows = [
      { resourceGroup: 'rg-a' },
      { resource_group: 'rg-b' },
      { name: 'no-rg' },
    ];
    expect(resourceGroupOf(rows[0])).toBe('rg-a');
    expect(resourceGroupOf(rows[2])).toBe('—');
    expect(uniqueResourceGroups(rows)).toEqual(['rg-a', 'rg-b']);
  });

  test('countActiveFilters ignores defaults and empty values', () => {
    expect(countActiveFilters(
      { q: 'x', sev: '', open: true },
      { open: true },
    )).toBe(1);
    expect(countActiveFilters({ q: '', sev: 'HIGH' }, {})).toBe(1);
  });
});
