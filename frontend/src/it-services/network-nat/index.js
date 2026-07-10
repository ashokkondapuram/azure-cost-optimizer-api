/**
 * network-nat IT service — frontend public API.
 * See it-services/network-nat/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'network-nat';
export const API_PATH = '/resources/natgateways';
export const CANONICAL_TYPE = 'network/nat';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'natgateways',
});
