import {
  groupFindingsByResourceGroup,
  groupFindingsByResourceType,
  resourceGroupFromArmId,
} from './optimizationGrouping';

describe('optimizationGrouping', () => {
  const findings = [
    {
      id: '1',
      resource_type: 'Microsoft.Compute/virtualMachines',
      resource_group: 'rg-apps',
      resource_id: '/subscriptions/sub/resourcegroups/rg-apps/providers/microsoft.compute/virtualmachines/vm1',
      estimated_savings_usd: 100,
    },
    {
      id: '2',
      resource_type: 'Microsoft.Compute/virtualMachines',
      resource_group: 'rg-apps',
      resource_id: '/subscriptions/sub/resourcegroups/rg-apps/providers/microsoft.compute/virtualmachines/vm2',
      estimated_savings_usd: 50,
    },
    {
      id: '3',
      resource_type: 'Microsoft.Storage/storageAccounts',
      resource_id: '/subscriptions/sub/resourcegroups/rg-data/providers/microsoft.storage/storageaccounts/sa1',
      estimated_savings_usd: 25,
    },
  ];

  it('groups findings by resource type with savings totals', () => {
    const groups = groupFindingsByResourceType(findings);
    expect(groups).toHaveLength(2);
    expect(groups[0].label).toContain('virtualMachines');
    expect(groups[0].items).toHaveLength(2);
    expect(groups[0].savings).toBe(150);
  });

  it('groups findings by resource group', () => {
    const groups = groupFindingsByResourceGroup(findings);
    expect(groups.map((g) => g.label).sort()).toEqual(['rg-apps', 'rg-data']);
    const apps = groups.find((g) => g.label === 'rg-apps');
    expect(apps.items).toHaveLength(2);
  });

  it('parses resource group from ARM id', () => {
    expect(resourceGroupFromArmId(findings[2].resource_id)).toBe('rg-data');
  });
});
