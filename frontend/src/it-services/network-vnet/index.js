/**
 * network-vnet IT service — frontend public API.
 * See it-services/network-vnet/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'network-vnet';
export const API_PATH = '/resources/vnets';
export const CANONICAL_TYPE = 'network/vnet';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'virtualnetworks',
});

export {
  formatVnetAddressSpace,
  enrichVnetRow,
  vnetDisplaySku,
} from './utils/vnetNormalize';
