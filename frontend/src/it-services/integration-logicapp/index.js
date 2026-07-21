/**
 * integration-logicapp IT service — frontend public API.
 * See it-services/integration-logicapp/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'integration-logicapp';
export const API_PATH = apiPathForCanonical('integration/logicapp');
export const CANONICAL_TYPE = 'integration/logicapp';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'workflows',
});
