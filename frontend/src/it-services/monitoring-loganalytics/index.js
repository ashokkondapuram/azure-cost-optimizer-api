/**
 * monitoring-loganalytics IT service — frontend public API.
 * See it-services/monitoring-loganalytics/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'monitoring-loganalytics';
export const API_PATH = apiPathForCanonical('monitoring/loganalytics');
export const CANONICAL_TYPE = 'monitoring/loganalytics';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'workspaces',
});
