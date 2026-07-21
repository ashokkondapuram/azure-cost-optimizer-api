/**
 * integration-apim IT service — frontend public API.
 * See it-services/integration-apim/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'integration-apim';
export const API_PATH = apiPathForCanonical('integration/apim');
export const CANONICAL_TYPE = 'integration/apim';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'service',
});
