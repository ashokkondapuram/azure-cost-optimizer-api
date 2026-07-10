/**
 * integration-apim IT service — frontend public API.
 * See it-services/integration-apim/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'integration-apim';
export const API_PATH = '/resources/apim';
export const CANONICAL_TYPE = 'integration/apim';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'service',
});
