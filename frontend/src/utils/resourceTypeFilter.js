/** Helpers for resource type cost filtering. */

export function allCanonicalTypes(catalog) {
  return (catalog?.types || []).map((t) => t.canonical);
}

/** Full catalog selection is equivalent to no filter (subscription total). */
export function normalizeResourceTypeSelection(selectedTypes, catalog) {
  if (!selectedTypes?.length) return [];
  const all = allCanonicalTypes(catalog);
  if (!all.length || selectedTypes.length < all.length) return selectedTypes;
  const set = new Set(selectedTypes);
  if (all.every((id) => set.has(id))) return [];
  return selectedTypes;
}

export function withResourceTypes(params, selectedTypes, catalog = null) {
  const normalized = catalog
    ? normalizeResourceTypeSelection(selectedTypes, catalog)
    : selectedTypes;
  if (!normalized?.length) return { ...params };
  return { ...params, resource_types: normalized.join(',') };
}

export function resourceTypeFilterSummary(selectedTypes, catalog) {
  if (!selectedTypes?.length) return null;
  const flat = catalog?.types || [];
  const labels = selectedTypes.map((id) => {
    const row = flat.find((t) => t.canonical === id);
    return row?.label || id;
  });
  if (labels.length === 1) return labels[0];
  if (labels.length === 2) return `${labels[0]} + ${labels[1]}`;
  return `${labels.length} types`;
}

export function toggleTypeSelection(selected, canonical) {
  const set = new Set(selected || []);
  if (set.has(canonical)) set.delete(canonical);
  else set.add(canonical);
  return [...set];
}

export function selectCategoryTypes(selected, categoryTypes, selectAll) {
  const set = new Set(selected || []);
  for (const row of categoryTypes || []) {
    if (selectAll) set.add(row.canonical);
    else set.delete(row.canonical);
  }
  return [...set];
}
