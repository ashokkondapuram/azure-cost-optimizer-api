/**
 * compute-snapshot IT service — frontend public API.
 * See it-services/compute-snapshot/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'compute-snapshot';
export const API_PATH = '/resources/snapshots';
export const CANONICAL_TYPE = 'compute/snapshot';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'snapshots',
});
