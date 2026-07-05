import {
  isArmResourceId,
  shortArmResourceLabel,
  azurePortalUrl,
  normalizeArmResourceId,
} from './armResourceLinks';

const DISK_ID = '/subscriptions/93ca908b-5732-440d-b712-f6d7951951c0/resourceGroups/MC_ziov2rg1eu2_ziov2rg1eu2_eastus2/providers/Microsoft.Compute/disks/cso-54802-pgcore';

describe('armResourceLinks', () => {
  test('detects ARM resource IDs', () => {
    expect(isArmResourceId(DISK_ID)).toBe(true);
    expect(isArmResourceId(DISK_ID.slice(1))).toBe(true);
    expect(isArmResourceId('cso-54802-pgcore')).toBe(false);
    expect(isArmResourceId('/subscriptions/x')).toBe(false);
  });

  test('shortens resource ID to resource name', () => {
    expect(shortArmResourceLabel(DISK_ID)).toBe('cso-54802-pgcore');
  });

  test('builds Azure portal URLs', () => {
    expect(azurePortalUrl(DISK_ID)).toBe(
      `https://portal.azure.com/#resource${DISK_ID}`,
    );
    expect(azurePortalUrl('not-an-arm-id')).toBeNull();
  });

  test('normalizes leading slash', () => {
    expect(normalizeArmResourceId(DISK_ID.slice(1))).toBe(DISK_ID);
  });
});
