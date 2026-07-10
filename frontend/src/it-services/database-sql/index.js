/**
 * database-sql IT service — frontend public API.
 * See it-services/database-sql/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'database-sql';
export const API_PATH = '/resources/sql';
export const CANONICAL_TYPE = 'database/sql';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'servers',
});
