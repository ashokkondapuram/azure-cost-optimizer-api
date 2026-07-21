/**
 * analytics-adx IT service — frontend public API.
 * See it-services/analytics-adx/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'analytics-adx';
export const API_PATH = apiPathForCanonical('analytics/adx');
export const CANONICAL_TYPE = 'analytics/adx';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'clusters',
});
