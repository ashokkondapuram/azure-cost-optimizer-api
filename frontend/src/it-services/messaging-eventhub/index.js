/**
 * messaging-eventhub IT service — frontend public API.
 * See it-services/messaging-eventhub/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';
import { apiPathForCanonical } from '../../config/resourceApiPaths';

export const SERVICE_ID = 'messaging-eventhub';
export const API_PATH = apiPathForCanonical('messaging/eventhub');
export const CANONICAL_TYPE = 'messaging/eventhub';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'namespaces',
});
