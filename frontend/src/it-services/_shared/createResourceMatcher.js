/**
 * Shared helpers for IT service frontend modules.
 */

export function createResourceMatcher({
  apiPath = '',
  canonicalType = '',
  armTypeHint = '',
} = {}) {
  const apiNeedle = String(apiPath || '').toLowerCase();
  const canonical = String(canonicalType || '').toLowerCase();
  const armHint = String(armTypeHint || '').toLowerCase();

  return function matchesResource(resource, apiPathArg = '') {
    const path = String(apiPathArg || '').toLowerCase();
    if (apiNeedle && path.includes(apiNeedle)) return true;

    const rowCanonical = String(
      resource?.canonical_type || resource?.canonicalType || '',
    ).toLowerCase();
    if (canonical && rowCanonical === canonical) return true;

    const type = String(resource?.type || '').toLowerCase();
    if (armHint && type.includes(armHint)) {
      if (armHint === 'virtualmachines' && type.includes('scalesets')) return false;
      return true;
    }

    return false;
  };
}
