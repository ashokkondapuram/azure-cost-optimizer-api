import { resourceRowId, INVENTORY_API_PATH } from './resourceRowId';
import { normalizeArmId } from './findingDedupe';

describe('resourceRowId', () => {
  it('normalizes row ids with trailing slash', () => {
    const id = '/subscriptions/abc/resourcegroups/rg/providers/microsoft.compute/virtualmachines/vm1/';
    expect(resourceRowId({ id })).toBe(normalizeArmId(id));
  });

  it('exports inventory api path constant', () => {
    expect(INVENTORY_API_PATH).toBe('/resources/from-cost');
  });
});
