/**
 * database-cosmosdb IT service — frontend public API.
 * See it-services/database-cosmosdb/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'database-cosmosdb';
export const API_PATH = '/resources/cosmosdb';
export const CANONICAL_TYPE = 'database/cosmosdb';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'databaseaccounts',
});
