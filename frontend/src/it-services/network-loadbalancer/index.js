/**
 * network-loadbalancer IT service — frontend public API.
 * See it-services/network-loadbalancer/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'network-loadbalancer';
export const API_PATH = '/resources/loadbalancers';
export const CANONICAL_TYPE = 'network/loadbalancer';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'loadbalancers',
});
