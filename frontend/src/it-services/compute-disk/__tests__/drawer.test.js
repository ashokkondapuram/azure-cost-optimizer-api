import {
  matchesResource,
  enrichInventoryContext,
  hideStateKpi,
  skipOverviewTiles,
  collapseMetricsSection,
  costDriversDefaultOpen,
} from '../drawer';

describe('compute-disk drawer behavior', () => {
  const disk = { type: 'Microsoft.Compute/disks' };

  test('matches disk resources by type and api path', () => {
    expect(matchesResource(disk)).toBe(true);
    expect(matchesResource({}, '/resources/disks')).toBe(true);
    expect(matchesResource({ type: 'Microsoft.Compute/snapshots' })).toBe(false);
  });

  test('enriches inventory context for disks', () => {
    expect(enrichInventoryContext({ sku: 'Premium_LRS' }, disk, '/resources/disks')).toEqual({
      sku: 'Premium_LRS',
      canonicalType: 'compute/disk',
      diskPropertiesShown: true,
    });
  });

  test('hides state kpi and overview tiles for disks', () => {
    expect(hideStateKpi(disk, '/resources/disks')).toBe(true);
    expect(skipOverviewTiles(disk, '/resources/disks')).toBe(true);
    expect(collapseMetricsSection(disk, '/resources/disks')).toBe(true);
  });

  test('defaults cost drivers closed for disks', () => {
    expect(costDriversDefaultOpen({
      resource: disk,
      apiPath: '/resources/disks',
      findingsCount: 3,
      triggerCount: 2,
    })).toBe(false);
    expect(costDriversDefaultOpen({
      resource: { type: 'Microsoft.Compute/virtualMachines' },
      apiPath: '/resources/vms',
      findingsCount: 1,
      triggerCount: 0,
    })).toBe(true);
  });
});
