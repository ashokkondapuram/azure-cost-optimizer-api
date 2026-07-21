import {
  actionResourceDisplayName,
  actionResourceMetaLine,
  actionResourceTypeLabel,
  countDistinctActionResources,
} from '../utils/actionUtils';

describe('action resource display helpers', () => {
  test('uses short name when resource_name is readable', () => {
    const action = {
      resource_name: 'prod-web-01',
      resource_type: 'Microsoft.Compute/virtualMachines',
      resource_id: '/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/prod-web-01',
    };
    expect(actionResourceDisplayName(action)).toBe('prod-web-01');
  });

  test('counts distinct resources with normalized ARM ids', () => {
    const actions = [
      { resource_id: '/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1/' },
      { resource_id: '/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1' },
      { resource_id: '/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-2' },
    ];
    expect(countDistinctActionResources(actions)).toBe(2);
  });

  test('falls back to last path segment for cost management style ids', () => {
    const action = {
      resource_name: 'Virtual Machines',
      resource_type: 'Virtual Machines',
      resource_id: '/subscriptions/x/providers/microsoft.costmanagement/services/virtual machines',
    };
    expect(actionResourceDisplayName(action)).toBe('Virtual Machines');
    expect(actionResourceTypeLabel(action)).toBe('Virtual Machines');
    expect(actionResourceMetaLine(action)).toContain('Virtual Machines');
  });
});
