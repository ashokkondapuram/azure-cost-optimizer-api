import { lookupAdvisorForResource, resourceArmIdCandidates } from './resourceAdvisorUtils';

describe('resourceAdvisorUtils', () => {
  it('collects multiple arm id fields', () => {
    const row = {
      id: '/subscriptions/s1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1',
      resource_id: '/subscriptions/s1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1/',
    };
    expect(resourceArmIdCandidates(row)).toHaveLength(1);
  });

  it('looks up advisor by alternate id fields', () => {
    const map = new Map();
    const rid = '/subscriptions/s1/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1';
    map.set(rid, [{ summary: 'Resize' }]);
    const row = { resource_id: rid };
    expect(lookupAdvisorForResource(map, row)).toHaveLength(1);
  });
});
