/**
 * analytics-mlworkspace IT service — frontend public API.
 * See it-services/analytics-mlworkspace/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'analytics-mlworkspace';
export const API_PATH = apiPathForCanonical('analytics/mlworkspace');
export const CANONICAL_TYPE = 'analytics/mlworkspace';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'workspaces',
});
