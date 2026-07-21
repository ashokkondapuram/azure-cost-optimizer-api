/**
 * compute-snapshot IT service — frontend public API.
 * See it-services/compute-snapshot/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'compute-snapshot';
export const API_PATH = apiPathForCanonical('compute/snapshot');
export const CANONICAL_TYPE = 'compute/snapshot';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'snapshots',
});
