/**
 * monitoring-loganalytics IT service — frontend public API.
 * See it-services/monitoring-loganalytics/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'monitoring-loganalytics';
export const API_PATH = '/resources/loganalytics';
export const CANONICAL_TYPE = 'monitoring/loganalytics';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'workspaces',
});
