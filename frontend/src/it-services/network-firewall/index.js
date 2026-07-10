/**
 * network-firewall IT service — frontend public API.
 * See it-services/network-firewall/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'network-firewall';
export const API_PATH = '/resources/firewall';
export const CANONICAL_TYPE = 'network/firewall';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'azurefirewalls',
});
