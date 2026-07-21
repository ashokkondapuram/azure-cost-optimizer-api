/** Shared client-side filtering helpers. */

const RIGHTSIZING_RULE_IDS = new Set([
  'VM_SKU_SIZING_EXTENDED',
  'VM_RIGHTSIZE_FAMILY',
  'VM_UNDERUTILIZED_EXTENDED',
  'VM_OVERSIZE',
  'VM_UNDERUTILIZED',
  'REDIS_RIGHTSIZE_EXTENDED',
]);

function parseEvidence(evidence) {
  if (!evidence) return {};
  if (typeof evidence === 'object') return evidence;
  try {
    return JSON.parse(evidence);
  } catch {
    return {};
  }
}

/** Cost optimization includes quantified savings and rightsizing (downsize, change family) without retail pricing. */
export function isCostOptimizationFinding(finding) {
  const savings = finding?.estimated_savings_usd || 0;
  if (savings > 0) return true;
  if (RIGHTSIZING_RULE_IDS.has(finding?.rule_id)) return true;
  const action = parseEvidence(finding?.evidence)?.sizing_action;
  return action === 'downgrade' || action === 'cross_family' || action === 'upgrade';
}

export function normalizeQuery(q) {
  return (q || '').trim().toLowerCase();
}

export function textIncludes(haystack, needle) {
  if (!needle) return true;
  return (haystack || '').toLowerCase().includes(needle);
}

export function matchResourceRow(row, query, extraFields = []) {
  const q = normalizeQuery(query);
  if (!q) return true;
  const parts = [
    row?.name,
    row?.resource_name,
    row?.resourceGroup,
    row?.resource_group,
    row?.location,
    row?.id,
    row?.resource_id,
    ...extraFields.map((fn) => (typeof fn === 'function' ? fn(row) : row?.[fn])),
  ];
  return parts.filter(Boolean).join(' ').toLowerCase().includes(q);
}

export function matchFinding(finding, query) {
  const q = normalizeQuery(query);
  if (!q) return true;
  const hay = [
    finding?.rule_name,
    finding?.rule_id,
    finding?.resource_name,
    finding?.resource_group,
    finding?.resource_type,
    finding?.detail,
    finding?.recommendation,
    finding?.impact,
    finding?.resource_id,
    finding?.category,
    finding?.severity,
  ].filter(Boolean).join(' ').toLowerCase();
  return hay.includes(q);
}

export function uniqueSorted(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) =>
    String(a).localeCompare(String(b)),
  );
}

export function resourceGroupOf(row) {
  return row?.resourceGroup || row?.resource_group || '—';
}

export function uniqueResourceGroups(rows) {
  return uniqueSorted(rows.map(resourceGroupOf).filter((rg) => rg !== '—'));
}

export function countActiveFilters(filters, defaults = {}) {
  return Object.entries(filters).filter(([key, val]) => {
    const def = defaults[key];
    if (val === def || val === '' || val === false || val == null) return false;
    return true;
  }).length;
}
