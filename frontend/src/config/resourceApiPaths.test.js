import {
  apiPathForCanonical,
  apiPathForCountKey,
  canonicalFromApiPath,
} from '../config/resourceApiPaths';

describe('resourceApiPaths', () => {
  it('maps count keys to canonical list paths', () => {
    expect(apiPathForCountKey('disks')).toBe('/resources/compute/disk');
    expect(apiPathForCountKey('aks')).toBe('/resources/containers/aks');
  });

  it('resolves legacy and canonical api paths to the same type', () => {
    expect(canonicalFromApiPath('/resources/disks')).toBe('compute/disk');
    expect(canonicalFromApiPath('/resources/compute/disk')).toBe('compute/disk');
  });

  it('builds canonical paths from canonical types', () => {
    expect(apiPathForCanonical('monitoring/loganalytics')).toBe('/resources/monitoring/loganalytics');
  });
});
