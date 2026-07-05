import {
  advisorCategoryLabel,
  indexAdvisorByResourceId,
  primaryAdvisorRecommendation,
} from './advisorUtils';

describe('advisorUtils', () => {
  it('labels advisor categories', () => {
    expect(advisorCategoryLabel('HighAvailability')).toBe('Reliability');
    expect(advisorCategoryLabel('Cost')).toBe('Cost');
  });

  it('indexes recommendations by resource id', () => {
    const map = indexAdvisorByResourceId([
      { resource_id: '/subscriptions/s/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1' },
      { resource_id: '/SUBSCRIPTIONS/S/RESOURCEGROUPS/RG/PROVIDERS/MICROSOFT.COMPUTE/VIRTUALMACHINES/VM1' },
    ]);
    expect(map.size).toBe(1);
  });

  it('picks highest-impact recommendation', () => {
    const primary = primaryAdvisorRecommendation([
      { impact: 'Low', potential_savings_monthly: 200 },
      { impact: 'High', potential_savings_monthly: 50 },
    ]);
    expect(primary.impact).toBe('High');
  });
});
