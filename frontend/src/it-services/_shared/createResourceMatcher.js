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
    const rowType = String(resource?.type || '').toLowerCase();
    if (canonical && (rowCanonical === canonical || rowType === canonical)) return true;

    const type = rowType;
    if (armHint && type.includes(armHint)) {
      if (armHint === 'virtualmachines' && type.includes('scalesets')) return false;
      return true;
    }

    return false;
  };
}
