/**
 * appservice-plan IT service — frontend public API.
 * See it-services/appservice-plan/manifest.yaml
 */

import { createResourceMatcher } from '../_shared/createResourceMatcher';

export const SERVICE_ID = 'appservice-plan';
export const API_PATH = '/resources/appserviceplans';
export const CANONICAL_TYPE = 'appservice/plan';

export const matchesResource = createResourceMatcher({
  apiPath: API_PATH,
  canonicalType: CANONICAL_TYPE,
  armTypeHint: 'serverfarms',
});
