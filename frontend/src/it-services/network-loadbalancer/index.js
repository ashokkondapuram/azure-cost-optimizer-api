/**
 * network-loadbalancer IT service — frontend public API.
 * See it-services/network-loadbalancer/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'network-loadbalancer';
export const API_PATH = apiPathForCanonical('network/loadbalancer');
export const CANONICAL_TYPE = 'network/loadbalancer';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'loadbalancers',
});
