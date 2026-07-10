/**
 * network-frontdoor IT service — frontend public API.
 * See it-services/network-frontdoor/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'network-frontdoor';
export const API_PATH = '/resources/frontdoor';
export const CANONICAL_TYPE = 'network/frontdoor';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'frontdoors',
});
