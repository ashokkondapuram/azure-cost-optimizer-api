/**
 * security-keyvault IT service — frontend public API.
 * See it-services/security-keyvault/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'security-keyvault';
export const API_PATH = '/resources/keyvaults';
export const CANONICAL_TYPE = 'security/keyvault';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'vaults',
});
