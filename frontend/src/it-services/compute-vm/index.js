/**
 * compute-vm IT service — frontend public API.
 * See it-services/compute-vm/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'compute-vm';
export const API_PATH = '/resources/vms';
export const CANONICAL_TYPE = 'compute/vm';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'virtualmachines',
});
