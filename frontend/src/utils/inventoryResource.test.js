import { isInventoryResource } from './inventoryResource';

describe('isInventoryResource', () => {
  it('returns true for synced inventory rows', () => {
    expect(isInventoryResource({ inInventory: true, costExportOnly: false })).toBe(true);
  });

  it('returns false for cost-export-only rows', () => {
    expect(isInventoryResource({ inInventory: false, costExportOnly: true })).toBe(false);
  });

  it('returns false for standalone VMSS rows', () => {
    expect(isInventoryResource({
      type: 'compute/vmss',
      id: '/subscriptions/s/resourceGroups/MC_rg/providers/Microsoft.Compute/virtualMachineScaleSets/aks-pool',
      inInventory: true,
      costExportOnly: false,
    })).toBe(false);
  });
});
