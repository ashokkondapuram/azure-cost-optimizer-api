import {
  findingCategoriesForTable,
  findingCategoryLabel,
  findingSeverityTone,
} from './findingTableUtils';

describe('findingTableUtils', () => {
  it('labels finding categories', () => {
    expect(findingCategoryLabel('RELIABILITY')).toBe('Reliability');
    expect(findingCategoryLabel('COST')).toBe('Cost');
  });

  it('maps severity to icon tone', () => {
    expect(findingSeverityTone('CRITICAL')).toBe('high');
    expect(findingSeverityTone('INFO')).toBe('muted');
  });

  it('returns engine categories in fixed order', () => {
    const categories = findingCategoriesForTable([
      { category: 'SECURITY', severity: 'LOW', rule_name: 'Open NSG' },
      { category: 'COMPUTE', severity: 'HIGH', rule_name: 'Idle VM' },
      { category: 'COST', severity: 'MEDIUM', rule_name: 'Right-size' },
      { category: 'COST', severity: 'HIGH', rule_name: 'Reserved instance' },
      { category: 'NETWORK', severity: 'MEDIUM', rule_name: 'Unused IP' },
    ]);
    expect(categories.map((item) => item.category)).toEqual(['COST', 'SECURITY', 'COMPUTE', 'NETWORK']);
    expect(categories[0].severity).toBe('HIGH');
  });
});
