/**
 * security-keyvault IT service — frontend public API.
 * See it-services/security-keyvault/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'security-keyvault';
export const API_PATH = apiPathForCanonical('security/keyvault');
export const CANONICAL_TYPE = 'security/keyvault';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'vaults',
});
