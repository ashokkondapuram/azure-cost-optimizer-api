import React from 'react';

/**
 * Footer for server-paginated inventory tables (load-more pattern).
 */
export default function ResourceTableFooter({
  shownCount,
  loadedCount,
  totalCount,
  hasFilters = false,
  hasMore = false,
  onLoadMore,
  isLoadingMore = false,
  hint = 'Click a row for details',
}) {
  return (
    <footer className="resource-table-footer">
      <span>
        {shownCount.toLocaleString()} shown · {loadedCount.toLocaleString()} loaded of {totalCount.toLocaleString()} total
        {hasFilters ? ' · Filters apply to loaded rows' : ''}
        {hint ? ` · ${hint}` : ''}
      </span>
      {hasMore && onLoadMore && (
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={onLoadMore}
          disabled={isLoadingMore}
        >
          {isLoadingMore ? 'Loading…' : 'Load more'}
        </button>
      )}
    </footer>
  );
}
