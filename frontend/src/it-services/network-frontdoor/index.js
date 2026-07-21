/**
 * network-frontdoor IT service — frontend public API.
 * See it-services/network-frontdoor/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'network-frontdoor';
export const API_PATH = apiPathForCanonical('network/frontdoor');
export const CANONICAL_TYPE = 'network/frontdoor';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'frontdoors',
});
