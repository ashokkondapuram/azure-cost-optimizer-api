/**
 * compute-vmss IT service — frontend public API.
 * See it-services/compute-vmss/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'compute-vmss';
export const API_PATH = '/resources/vmss';
export const CANONICAL_TYPE = 'compute/vmss';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'virtualmachinescalesets',
});
