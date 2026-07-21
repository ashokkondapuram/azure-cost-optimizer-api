/** Fetch all open findings pages for subscription index builds. */
import { fetchFindingsPage } from '../api/azure';

export const FINDINGS_PAGE_SIZE = 500;
export const FINDINGS_INDEX_MAX = 10000;

export async function fetchAllOpenFindings(subscription, { inventoryOnly = false } = {}) {
  let offset = 0;
  let allItems = [];
  let total = 0;

  while (offset < FINDINGS_INDEX_MAX) {
    const page = await fetchFindingsPage({
      subscription_id: subscription,
      status: 'open',
      limit: FINDINGS_PAGE_SIZE,
      offset,
      sort_by: 'priority',
      ...(inventoryOnly ? { inventory_only: true } : {}),
    });
    const batch = page?.items || [];
    allItems = allItems.concat(batch);
    total = page?.total ?? allItems.length;
    offset += FINDINGS_PAGE_SIZE;
    if (!batch.length || !page?.has_more || allItems.length >= total) break;
  }

  return {
    items: allItems,
    total,
    truncated: allItems.length < total,
  };
}
