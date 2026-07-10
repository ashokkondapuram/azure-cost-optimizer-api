/**
 * analytics-synapse IT service — frontend public API.
 * See it-services/analytics-synapse/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'analytics-synapse';
export const API_PATH = '/resources/synapse';
export const CANONICAL_TYPE = 'analytics/synapse';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'workspaces',
});
