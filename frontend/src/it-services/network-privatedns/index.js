/**
 * network-privatedns IT service — frontend public API.
 * See it-services/network-privatedns/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'network-privatedns';
export const API_PATH = '/resources/privatedns';
export const CANONICAL_TYPE = 'network/privatedns';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'privatednszones',
});

export {
  formatPrivateDnsZoneSummary,
  enrichPrivateDnsRow,
  privateDnsDisplaySummary,
} from './utils/privateDnsNormalize';
