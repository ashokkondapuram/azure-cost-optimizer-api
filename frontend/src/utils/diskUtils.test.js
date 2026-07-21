import { diskLastOwnershipUpdate, isDiskResource } from './diskUtils';

describe('diskUtils', () => {
  test('detects disk resources', () => {
    expect(isDiskResource({ type: 'Microsoft.Compute/disks' })).toBe(true);
    expect(isDiskResource({}, '/resources/disks')).toBe(true);
    expect(isDiskResource({ type: 'Microsoft.Compute/snapshots' })).toBe(false);
  });

  test('reads last ownership update from synced properties only', () => {
    expect(diskLastOwnershipUpdate({
      properties: { lastOwnershipUpdateTime: '2026-04-23T12:11:15Z' },
    })).toBe('2026-04-23T12:11:15Z');
    expect(diskLastOwnershipUpdate({ lastOwnershipUpdateTime: '2026-04-23T12:11:15Z' }))
      .toBeNull();
  });
});
