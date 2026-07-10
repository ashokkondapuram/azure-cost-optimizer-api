/**
 * integration-logicapp IT service — frontend public API.
 * See it-services/integration-logicapp/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'integration-logicapp';
export const API_PATH = '/resources/logicapps';
export const CANONICAL_TYPE = 'integration/logicapp';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'workflows',
});
