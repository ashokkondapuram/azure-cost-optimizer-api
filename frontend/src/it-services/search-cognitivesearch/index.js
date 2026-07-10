/**
 * search-cognitivesearch IT service — frontend public API.
 * See it-services/search-cognitivesearch/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'search-cognitivesearch';
export const API_PATH = '/resources/cognitivesearch';
export const CANONICAL_TYPE = 'search/cognitivesearch';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'searchservices',
});
