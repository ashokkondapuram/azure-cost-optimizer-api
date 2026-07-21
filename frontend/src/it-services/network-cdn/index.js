/**
 * network-cdn IT service — frontend public API.
 * See it-services/network-cdn/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'network-cdn';
export const API_PATH = apiPathForCanonical('network/cdn');
export const CANONICAL_TYPE = 'network/cdn';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'profiles',
});
