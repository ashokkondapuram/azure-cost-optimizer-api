/**
 * network-cdn IT service — frontend public API.
 * See it-services/network-cdn/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'network-cdn';
export const API_PATH = '/resources/cdn';
export const CANONICAL_TYPE = 'network/cdn';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'profiles',
});
