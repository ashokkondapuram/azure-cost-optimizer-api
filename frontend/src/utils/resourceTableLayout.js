/** Enable capped in-table scroll only when the list is long enough to need it. */
export const RESOURCE_TABLE_SCROLL_THRESHOLD = 12;

export function resourceTableWrapClass(rowCount, baseClass = 'table-wrap resource-table-wrap') {
  const scrollable = Number(rowCount) > RESOURCE_TABLE_SCROLL_THRESHOLD;
  return scrollable ? `${baseClass} resource-table-wrap--scrollable` : baseClass;
}
