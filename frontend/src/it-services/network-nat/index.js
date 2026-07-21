/**
 * network-nat IT service — frontend public API.
 * See it-services/network-nat/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'network-nat';
export const API_PATH = apiPathForCanonical('network/nat');
export const CANONICAL_TYPE = 'network/nat';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'natgateways',
});
