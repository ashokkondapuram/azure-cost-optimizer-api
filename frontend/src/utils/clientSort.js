/** Client-side table sorting helpers. */

export function toggleSort(currentKey, currentDir, nextKey) {
  if (currentKey !== nextKey) return { key: nextKey, direction: 'asc' };
  return { key: nextKey, direction: currentDir === 'asc' ? 'desc' : 'asc' };
}

export function sortRows(rows, sortKey, direction, accessors = {}) {
  if (!sortKey || !rows?.length) return rows || [];
  const dir = direction === 'desc' ? -1 : 1;
  const get = accessors[sortKey] || ((row) => row[sortKey]);

  return [...rows].sort((a, b) => {
    const av = get(a);
    const bv = get(b);
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === 'number' && typeof bv === 'number') {
      return (av - bv) * dir;
    }
    return String(av).localeCompare(String(bv), undefined, { numeric: true, sensitivity: 'base' }) * dir;
  });
}
