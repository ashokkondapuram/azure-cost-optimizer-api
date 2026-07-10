/**
 * network-trafficmanager IT service — frontend public API.
 * See it-services/network-trafficmanager/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'network-trafficmanager';
export const API_PATH = '/resources/trafficmanager';
export const CANONICAL_TYPE = 'network/trafficmanager';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'trafficmanagerprofiles',
});
