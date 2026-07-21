import {
  enrichInventoryContext,
  resolveCostDriversDefaultOpen,
  resolvePropertiesPanel,
  resolveItServiceUi,
  shouldHideStateKpi,
  shouldSkipOverviewTiles,
  shouldCollapseMetricsSection,
} from './registry';

describe('it-services registry', () => {
  const disk = { type: 'Microsoft.Compute/disks' };

  test('resolves compute-disk service UI', () => {
    const mod = resolveItServiceUi(disk, '/resources/disks');
    expect(mod?.SERVICE_ID).toBe('compute-disk');
  });

  test('wires disk drawer behavior through registry', () => {
    expect(shouldSkipOverviewTiles(disk, '/resources/disks')).toBe(true);
    expect(shouldCollapseMetricsSection(disk, '/resources/disks')).toBe(true);
    expect(shouldHideStateKpi(disk, '/resources/disks')).toBe(true);
    expect(resolvePropertiesPanel(disk, '/resources/disks')).toBeTruthy();
    expect(enrichInventoryContext({}, disk, '/resources/disks').diskPropertiesShown).toBe(true);
    expect(resolveCostDriversDefaultOpen({
      resource: disk,
      apiPath: '/resources/disks',
      findingsCount: 2,
      triggerCount: 1,
    })).toBe(false);
  });
});
