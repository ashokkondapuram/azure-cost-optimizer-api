import { normalizeArmId } from './findingDedupe';

/** Canonical ARM id for inventory rows, findings index, and drawer lookups. */
export function resourceRowId(rowOrId) {
  if (typeof rowOrId === 'string') return normalizeArmId(rowOrId);
  return normalizeArmId(rowOrId?.id || rowOrId?.resource_id || '');
}

export const INVENTORY_API_PATH = '/resources/from-cost';

export function inventoryQueryPredicate(query) {
  const key = query?.queryKey;
  return Array.isArray(key)
    && key[0] === INVENTORY_API_PATH
    && typeof key[1] === 'string';
}
