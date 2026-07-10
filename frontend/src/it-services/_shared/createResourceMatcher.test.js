import { createResourceMatcher } from '../_shared/createResourceMatcher';

describe('createResourceMatcher', () => {
  const matchVm = createResourceMatcher({
    apiPath: '/resources/vms',
    canonicalType: 'compute/vm',
    armTypeHint: 'virtualmachines',
  });

  test('matches by api path', () => {
    expect(matchVm({}, '/resources/vms')).toBe(true);
    expect(matchVm({}, '/resources/disks')).toBe(false);
  });

  test('matches by canonical type on resource', () => {
    expect(matchVm({ canonical_type: 'compute/vm' }, '')).toBe(true);
  });

  test('matches by arm type hint', () => {
    expect(matchVm({ type: 'Microsoft.Compute/virtualMachines' }, '')).toBe(true);
    expect(matchVm({ type: 'Microsoft.Compute/virtualMachineScaleSets' }, '')).toBe(false);
  });
});
