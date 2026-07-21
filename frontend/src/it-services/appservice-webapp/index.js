/**
 * appservice-webapp IT service — frontend public API.
 * See it-services/appservice-webapp/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'appservice-webapp';
export const API_PATH = apiPathForCanonical('appservice/webapp');
export const CANONICAL_TYPE = 'appservice/webapp';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'sites',
});

export {
  formatAppServicePlanSku,
  formatAppServiceWebappSku,
  enrichAppServicePlanRow,
  enrichAppServiceWebappRow,
  appServicePlanDisplaySku,
  appServiceWebappDisplaySku,
} from './utils/appServiceNormalize';
