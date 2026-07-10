import { useCallback, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { normalizeArmResourceId } from '../utils/armResourceLinks';

function findInspectMatch(items, getResourceId, resourceIdParam, searchQuery) {
  if (!items?.length) return null;
  if (resourceIdParam) {
    const target = normalizeArmResourceId(resourceIdParam).toLowerCase();
    return items.find((item) => getResourceId(item) === target) || null;
  }
  if (searchQuery) {
    const q = searchQuery.trim().toLowerCase();
    return items.find((item) => {
      const name = String(item.name || '').toLowerCase();
      const id = getResourceId(item);
      return name === q || id.endsWith(`/${q}`);
    }) || null;
  }
  return null;
}

/**
 * Opens a resource drawer when the URL includes inspect=1 (from inventoryInspectLink).
 */
export default function useInventoryInspectDeepLink({
  items,
  isLoading,
  isLoadingMore = false,
  getResourceId,
  hasMore,
  loadMore,
  onOpen,
  enabled = true,
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const pendingRef = useRef(false);
  const openedRef = useRef(false);
  const lastLoadedCountRef = useRef(0);
  const stalledLoadsRef = useRef(0);

  const inspect = searchParams.get('inspect') === '1';
  const section = searchParams.get('section');
  const resourceIdParam = searchParams.get('resourceId');
  const searchQuery = searchParams.get('search');
  const hasTarget = Boolean(resourceIdParam || searchQuery?.trim());

  const clearInspectParams = useCallback(() => {
    const next = new URLSearchParams(searchParams);
    next.delete('inspect');
    next.delete('section');
    next.delete('resourceId');
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    openedRef.current = false;
    pendingRef.current = inspect && hasTarget;
    lastLoadedCountRef.current = 0;
    stalledLoadsRef.current = 0;
  }, [inspect, hasTarget, resourceIdParam, searchQuery, section]);

  useEffect(() => {
    if (!enabled || !pendingRef.current || openedRef.current || isLoading || isLoadingMore) return;

    if (!hasTarget) {
      pendingRef.current = false;
      if (inspect) clearInspectParams();
      return;
    }

    const loadedCount = items?.length ?? 0;
    if (loadedCount === lastLoadedCountRef.current) {
      stalledLoadsRef.current += 1;
    } else {
      stalledLoadsRef.current = 0;
      lastLoadedCountRef.current = loadedCount;
    }

    const match = findInspectMatch(items, getResourceId, resourceIdParam, searchQuery);
    if (match) {
      openedRef.current = true;
      pendingRef.current = false;
      onOpen(match, section || 'advanced-analysis');
      clearInspectParams();
      return;
    }

    if (hasMore && stalledLoadsRef.current < 2) {
      loadMore?.();
      return;
    }

    pendingRef.current = false;
    clearInspectParams();
  }, [
    enabled,
    isLoading,
    isLoadingMore,
    items,
    getResourceId,
    resourceIdParam,
    searchQuery,
    section,
    hasMore,
    loadMore,
    onOpen,
    clearInspectParams,
    hasTarget,
    inspect,
  ]);
}
