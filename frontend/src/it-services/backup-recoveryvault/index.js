/**
 * backup-recoveryvault IT service — frontend public API.
 * See it-services/backup-recoveryvault/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'backup-recoveryvault';
export const API_PATH = apiPathForCanonical('backup/recoveryvault');
export const CANONICAL_TYPE = 'backup/recoveryvault';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'vaults',
});
