import {
  findNextMaintenanceWindow,
  iconKeyForMaintenanceItem,
  categoryLabel,
  maintenanceCategory,
  isUpcomingWindow,
  isWindowCompleted,
  urgencyFor,
} from './maintenanceUtils';

describe('maintenanceUtils', () => {
  const now = new Date('2026-07-06T12:00:00Z').getTime();

  it('marks past activity log events as completed', () => {
    const item = {
      source: 'activity_log',
      window_start: '2026-05-26T23:00:00Z',
    };
    expect(isWindowCompleted(item, now)).toBe(true);
    expect(urgencyFor(item, now)).toBe('completed');
    expect(isUpcomingWindow(item, now)).toBe(false);
  });

  it('picks the earliest future window as next', () => {
    const items = [
      { id: 'past', source: 'vm', window_start: '2026-05-26T23:00:00Z' },
      { id: 'future', source: 'vm', window_start: '2026-07-10T01:00:00Z', window_end: '2026-07-10T05:00:00Z' },
      { id: 'later', source: 'health_event', window_start: '2026-08-01T00:00:00Z' },
    ];
    const next = findNextMaintenanceWindow(items, now);
    expect(next?.id).toBe('future');
  });

  it('treats in-progress windows as upcoming', () => {
    const item = {
      source: 'vm',
      window_start: '2026-07-05T01:00:00Z',
      window_end: '2026-07-07T01:00:00Z',
    };
    expect(isUpcomingWindow(item, now)).toBe(true);
    expect(isWindowCompleted(item, now)).toBe(false);
  });

  it('maps maintenance sources to Azure icons', () => {
    expect(iconKeyForMaintenanceItem({ source: 'health_event' })).toBe('serviceHealth');
    expect(iconKeyForMaintenanceItem({ source: 'vm' })).toBe('virtualMachine');
    expect(iconKeyForMaintenanceItem({ source: 'vmss' })).toBe('vmScaleSets');
    expect(iconKeyForMaintenanceItem({
      source: 'activity_log',
      resource_type: 'VM scale set',
    })).toBe('vmScaleSets');
    expect(iconKeyForMaintenanceItem({
      source: 'vm',
      resource_id: '/subscriptions/x/resourcegroups/rg/providers/Microsoft.Compute/virtualMachines/vm1',
    })).toBe('virtualMachine');
    expect(iconKeyForMaintenanceItem({ source: 'unknown', resource_id: '/subscriptions/x/...' })).toBe(null);
  });

  it('maps legacy activity log rows to VM scale set category', () => {
    expect(maintenanceCategory({
      source: 'activity_log',
      resource_type: 'VM scale set',
    })).toBe('vmss');
    expect(categoryLabel({
      source: 'vmss',
      resource_type: 'VM scale set',
    })).toBe('VM scale set');
  });
});
