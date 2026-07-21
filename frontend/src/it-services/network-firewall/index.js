/**
 * network-firewall IT service — frontend public API.
 * See it-services/network-firewall/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'network-firewall';
export const API_PATH = apiPathForCanonical('network/firewall');
export const CANONICAL_TYPE = 'network/firewall';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'azurefirewalls',
});
