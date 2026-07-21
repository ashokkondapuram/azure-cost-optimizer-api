/**
 * integration-datafactory IT service — frontend public API.
 * See it-services/integration-datafactory/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'integration-datafactory';
export const API_PATH = apiPathForCanonical('integration/datafactory');
export const CANONICAL_TYPE = 'integration/datafactory';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'factories',
});
