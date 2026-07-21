/** Build engine rules URL, optionally focused on one Azure component. */
export function engineRulesUrl(component) {
  if (!component) return '/engine';
  return `/engine?component=${encodeURIComponent(component)}`;
}

/** DOM id for a component section on the engine config page. */
export function engineComponentSectionId(component) {
  const slug = String(component || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
  return `engine-component-${slug || 'all'}`;
}
