/**
 * messaging-eventhub IT service — frontend public API.
 * See it-services/messaging-eventhub/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'messaging-eventhub';
export const API_PATH = '/resources/eventhubs';
export const CANONICAL_TYPE = 'messaging/eventhub';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'namespaces',
});
