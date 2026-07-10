import { getDrawerOverviewTiles } from './resourceDrawerUtils';

describe('getDrawerOverviewTiles', () => {
  test('includes inventory fields without cost tile', () => {
    const tiles = getDrawerOverviewTiles({
      location: 'eastus',
      resourceGroup: 'rg-prod',
      state: 'running',
      sku: 'Standard_D2s_v3',
    });

    expect(tiles.some((t) => /cost/i.test(t.label))).toBe(false);
    expect(tiles.map((t) => t.label)).toEqual(
      expect.arrayContaining(['Location', 'Resource group', 'State', 'SKU']),
    );
  });

  test('includes AKS-specific fields when present', () => {
    const tiles = getDrawerOverviewTiles({
      _version: '1.29.2',
      _nodeCount: 3,
      location: 'westus',
    });

    expect(tiles.map((t) => t.label)).toEqual(
      expect.arrayContaining(['Version', 'Nodes', 'Location']),
    );
  });

  test('returns no overview tiles for disks (properties panel covers inventory)', () => {
    const tiles = getDrawerOverviewTiles(
      {
        type: 'Microsoft.Compute/disks',
        location: 'eastus',
        resourceGroup: 'rg-prod',
        state: 'Unattached',
        sku: 'Premium_LRS',
      },
      { apiPath: '/resources/disks' },
    );

    expect(tiles).toEqual([]);
  });
});
