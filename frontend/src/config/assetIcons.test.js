import { serviceDisplayNameForRow } from './assetIcons';

describe('serviceDisplayNameForRow', () => {
  it('prefers billing azureServiceName', () => {
    expect(serviceDisplayNameForRow({
      azureServiceName: 'Bandwidth',
      type: 'compute/vm',
    })).toBe('Bandwidth');
  });

  it('falls back to canonical type label when billing name is missing', () => {
    expect(serviceDisplayNameForRow({
      type: 'compute/disk',
    })).toBe('Managed Disks');
  });

  it('falls back to stub engine monitoring types', () => {
    expect(serviceDisplayNameForRow({
      type: 'monitoring/loganalytics',
    })).toBe('Monitoring');
  });

  it('falls back from ARM resource id', () => {
    expect(serviceDisplayNameForRow({
      id: '/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/disks/d1',
    })).toBe('Managed disk');
  });
});
