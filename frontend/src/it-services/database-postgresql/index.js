/**
 * database-postgresql IT service — frontend public API.
 * See it-services/database-postgresql/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'database-postgresql';
export const API_PATH = '/resources/postgresql';
export const CANONICAL_TYPE = 'database/postgresql';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'flexibleservers',
});
