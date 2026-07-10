/**
 * containers-aks IT service — frontend public API.
 * See it-services/containers-aks/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'containers-aks';
export const API_PATH = '/resources/aks';
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
