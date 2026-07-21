/**
 * network-privateendpoint IT service — frontend public API.
 * See it-services/network-privateendpoint/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'network-privateendpoint';
export const API_PATH = apiPathForCanonical('network/privateendpoint');
export const CANONICAL_TYPE = 'network/privateendpoint';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'privateendpoints',
});

export {
  formatPrivateEndpointConnection,
  enrichPrivateEndpointRow,
  privateEndpointDisplayConnection,
} from './utils/privateEndpointNormalize';
