/**
 * containers-acr IT service — frontend public API.
 * See it-services/containers-acr/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'containers-acr';
export const API_PATH = apiPathForCanonical('containers/acr');
export const CANONICAL_TYPE = 'containers/acr';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'registries',
});
