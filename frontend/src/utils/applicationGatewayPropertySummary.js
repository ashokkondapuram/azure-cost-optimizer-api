import { createResourceMatcher } from '../it-services/_shared/createResourceMatcher';

/** ARM / canonical matchers for Application Gateway resources. */
export const matchesApplicationGateway = createResourceMatcher({
  apiPath: '/resources/appgateways',
  canonicalType: 'network/appgateway',
  armTypeHint: 'applicationgateways',
});

/**
 * ARM property keys summarized as counts in drawer Essentials.
 * Full nested arrays/objects render as labeled group cards in Overview.
 */
export const APPLICATION_GATEWAY_SUMMARY_PROPERTY_KEYS = new Set([
  'backendAddressPools',
  'backendaddresspools',
  'probes',
  'healthProbes',
  'healthprobes',
  'httpListeners',
  'httplisteners',
  'requestRoutingRules',
  'requestroutingrules',
  'backendHttpSettingsCollection',
  'backendhttpsettingscollection',
  'frontendIPConfigurations',
  'frontendipconfigurations',
  'frontendPorts',
  'frontendports',
]);

function normalizePropertyKey(key) {
  return String(key || '').trim().toLowerCase().replace(/[._-]+/g, '');
}

function arrayCount(value) {
  return Array.isArray(value) ? value.length : null;
}

function listenerRefId(listenerRef) {
  if (!listenerRef || typeof listenerRef !== 'object') return '';
  return String(listenerRef.id || '').trim().toLowerCase();
}

/**
 * Count HTTP listeners — mirrors backend http_listener_count fallback logic.
 * @param {object} [properties]
 */
export function httpListenerCount(properties = {}) {
  const listeners = properties.httpListeners;
  if (Array.isArray(listeners) && listeners.length) {
    return listeners.length;
  }

  const refs = new Set();
  for (const rule of properties.requestRoutingRules || []) {
    if (!rule || typeof rule !== 'object') continue;
    const ref = listenerRefId((rule.properties || {}).httpListener);
    if (ref) refs.add(ref);
  }
  return refs.size || null;
}

/** True when the drawer resource is an Application Gateway. */
export function isApplicationGatewayResource(resource, apiPath = '') {
  return matchesApplicationGateway(resource, apiPath);
}

/** True when an ARM property key should be summarized, not expanded. */
export function isApplicationGatewaySummaryPropertyKey(key) {
  const normalized = normalizePropertyKey(key);
  if (!normalized) return false;
  return APPLICATION_GATEWAY_SUMMARY_PROPERTY_KEYS.has(normalized)
    || APPLICATION_GATEWAY_SUMMARY_PROPERTY_KEYS.has(String(key || '').trim());
}

/**
 * Summary count rows for Application Gateway Essentials.
 * @param {object} [properties]
 */
export function buildApplicationGatewaySummaryRows(properties = {}) {
  const props = properties || {};
  const entries = [
    ['Backend pools', arrayCount(props.backendAddressPools)],
    ['Health probes', arrayCount(props.probes) ?? arrayCount(props.healthProbes)],
    ['Listeners', httpListenerCount(props)],
    ['Rules', arrayCount(props.requestRoutingRules)],
  ];

  return entries
    .filter(([, count]) => count != null)
    .map(([label, count]) => ({
      key: `agw-${label.toLowerCase().replace(/\s+/g, '-')}`,
      label,
      value: String(count),
    }));
}
