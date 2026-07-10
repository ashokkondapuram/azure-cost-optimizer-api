/**
 * network-appgateway IT service — frontend public API.
 * See it-services/network-appgateway/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'network-appgateway';
export const API_PATH = '/resources/appgateways';
export const CANONICAL_TYPE = 'network/appgateway';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'applicationgateways',
});
