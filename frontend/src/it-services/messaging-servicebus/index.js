/**
 * messaging-servicebus IT service — frontend public API.
 * See it-services/messaging-servicebus/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'messaging-servicebus';
export const API_PATH = apiPathForCanonical('messaging/servicebus');
export const CANONICAL_TYPE = 'messaging/servicebus';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'namespaces',
});
