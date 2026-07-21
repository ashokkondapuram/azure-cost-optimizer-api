/**
 * network-nic IT service — frontend public API.
 * See it-services/network-nic/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'network-nic';
export const API_PATH = apiPathForCanonical('network/nic');
export const CANONICAL_TYPE = 'network/nic';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'networkinterfaces',
});
