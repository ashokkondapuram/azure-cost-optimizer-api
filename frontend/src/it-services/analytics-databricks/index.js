/**
 * analytics-databricks IT service — frontend public API.
 * See it-services/analytics-databricks/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'analytics-databricks';
export const API_PATH = '/resources/databricks';
export const CANONICAL_TYPE = 'analytics/databricks';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'workspaces',
});
