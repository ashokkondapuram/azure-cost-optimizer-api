/**
 * database-redis IT service — frontend public API.
 * See it-services/database-redis/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'database-redis';
export const API_PATH = apiPathForCanonical('database/redis');
export const CANONICAL_TYPE = 'database/redis';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'redis',
});
