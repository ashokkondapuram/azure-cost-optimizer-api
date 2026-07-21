/**
 * database-cosmosdb IT service — frontend public API.
 * See it-services/database-cosmosdb/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'database-cosmosdb';
export const API_PATH = apiPathForCanonical('database/cosmosdb');
export const CANONICAL_TYPE = 'database/cosmosdb';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'databaseaccounts',
});
