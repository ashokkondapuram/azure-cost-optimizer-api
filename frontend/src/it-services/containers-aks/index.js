/**
 * containers-aks IT service — frontend public API.
 * See it-services/containers-aks/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'containers-aks';
export const API_PATH = apiPathForCanonical('containers/aks');
export const CANONICAL_TYPE = 'containers/aks';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'managedclusters',
});

export {
  normalizeAksPools,
  normalizeAksCluster,
  dedupeAksClusters,
} from './utils/aksNormalize';

export { enrichDrawerResource } from './drawer';
