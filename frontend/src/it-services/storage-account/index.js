/**
 * storage-account IT service — frontend public API.
 * See it-services/storage-account/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'storage-account';
export const API_PATH = '/resources/storage';
export const CANONICAL_TYPE = 'storage/account';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'storageaccounts',
});
