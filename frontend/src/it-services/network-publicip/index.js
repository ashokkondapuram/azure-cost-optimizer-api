/**
 * network-publicip IT service — frontend public API.
 * See it-services/network-publicip/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'network-publicip';
export const API_PATH = apiPathForCanonical('network/publicip');
export const CANONICAL_TYPE = 'network/publicip';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'publicipaddresses',
});
