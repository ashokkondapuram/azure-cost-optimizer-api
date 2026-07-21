/**
 * network-expressroute IT service — frontend public API.
 * See it-services/network-expressroute/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'network-expressroute';
export const API_PATH = apiPathForCanonical('network/expressroute');
export const CANONICAL_TYPE = 'network/expressroute';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'expressroutecircuits',
});
