/**
 * monitoring-appinsights IT service — frontend public API.
 * See it-services/monitoring-appinsights/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'monitoring-appinsights';
export const API_PATH = '/resources/appinsights';
export const CANONICAL_TYPE = 'monitoring/appinsights';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'components',
});
