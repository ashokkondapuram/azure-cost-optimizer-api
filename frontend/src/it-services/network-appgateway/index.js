/**
 * network-appgateway IT service — frontend public API.
 * See it-services/network-appgateway/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'network-appgateway';
export const API_PATH = apiPathForCanonical('network/appgateway');
export const CANONICAL_TYPE = 'network/appgateway';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'applicationgateways',
});
