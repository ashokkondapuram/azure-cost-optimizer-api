/** Resolve Azure Advisor recommendations for an inventory row (multiple ARM id shapes). */

import { normalizeAdvisorResourceId } from './advisorUtils';

export function resourceArmIdCandidates(row) {
  const raw = [
    row?.id,
    row?.resource_id,
    row?.resourceId,
    row?.azureResourceId,
  ];
  const normalized = raw
    .map((v) => normalizeAdvisorResourceId(v))
    .filter(Boolean);
  return [...new Set(normalized)];
}

export function lookupAdvisorForResource(byResourceId, row) {
  if (!byResourceId || !row) return [];
  for (const rid of resourceArmIdCandidates(row)) {
    const recs = byResourceId.get(rid);
    if (recs?.length) return recs;
  }
  return [];
}

export function armResourceTypeFromId(resourceId) {
  const rid = normalizeAdvisorResourceId(resourceId);
  if (!rid) return 'Unknown';
  const marker = '/providers/';
  const idx = rid.indexOf(marker);
  if (idx < 0) return 'Subscription';
  const tail = rid.slice(idx + marker.length);
  const slash = tail.indexOf('/');
  return slash >= 0 ? tail.slice(0, slash) : tail;
}

export function armResourceShortName(resourceId) {
  const rid = normalizeAdvisorResourceId(resourceId);
  if (!rid) return '—';
  return rid.split('/').pop() || rid;
}
