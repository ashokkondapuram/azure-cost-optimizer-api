/**
 * network-privatelinkservice IT service — frontend public API.
 * See it-services/network-privatelinkservice/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'network-privatelinkservice';
export const API_PATH = '/resources/privatelinkservices';
export const CANONICAL_TYPE = 'network/privatelinkservice';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'privatelinkservices',
});

export {
  formatPrivateLinkServiceSummary,
  enrichPrivateLinkServiceRow,
  privateLinkServiceDisplaySummary,
} from './utils/privateLinkServiceNormalize';
