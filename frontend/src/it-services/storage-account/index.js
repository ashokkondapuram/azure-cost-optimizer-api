/**
 * storage-account IT service — frontend public API.
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';
export {
  formatAccessTier,
  formatReplicationSku,
  formatStorageMetric,
  isStorageResource,
  normalizeStorageProperties,
  storagePropertyRows,
  MISSING_DISPLAY,
} from './utils/storageUtils';

export const SERVICE_ID = 'storage-account';
export const API_PATH = apiPathForCanonical('storage/account');
export const CANONICAL_TYPE = 'storage/account';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'storageaccounts',
});
