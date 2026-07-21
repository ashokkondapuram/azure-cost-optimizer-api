/** Map engine finding categories to waste heatmap display categories. */
const HEATMAP_CATEGORY_BY_ENGINE = {
  COMPUTE: 'Compute',
  KUBERNETES: 'Kubernetes',
  STORAGE: 'Storage',
  NETWORK: 'Network',
  DATABASE: 'Database',
  SECURITY: 'Security',
  COST: 'Cost',
  GOVERNANCE: 'Governance',
  RELIABILITY: 'Reliability',
};

export function heatmapCategoryFromEngine(category) {
  const key = String(category || '').trim().toUpperCase();
  return HEATMAP_CATEGORY_BY_ENGINE[key] || category || null;
}

/** Build a deep link into the waste heatmap with optional filters. */
export function wasteHeatmapLink({ category, severity, ruleId } = {}) {
  const params = new URLSearchParams();
  const resolvedCategory = heatmapCategoryFromEngine(category) || category;
  if (resolvedCategory) params.set('category', resolvedCategory);
  if (severity) params.set('severity', String(severity).toLowerCase());
  if (ruleId) params.set('rule', ruleId);
  const qs = params.toString();
  return `/waste-heatmap${qs ? `?${qs}` : ''}`;
}

/** Parse waste heatmap URL search params into filter state. */
export function wasteHeatmapFiltersFromSearchParams(searchParams) {
  const category = searchParams.get('category') || null;
  const severity = searchParams.get('severity') || null;
  const ruleId = searchParams.get('rule') || searchParams.get('ruleId') || null;
  return { category, severity, ruleId };
}
