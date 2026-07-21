/**
 * network-nsg IT service — frontend public API.
 * See it-services/network-nsg/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'network-nsg';
export const API_PATH = apiPathForCanonical('network/nsg');
export const CANONICAL_TYPE = 'network/nsg';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'networksecuritygroups',
});
