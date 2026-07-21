import React from 'react';
import { Search, SlidersHorizontal } from 'lucide-react';

export default function WizCommandBar({
  search,
  onSearchChange,
  searchPlaceholder = 'Search…',
  sort,
  onSortChange,
  sortOptions = [],
  chips = [],
  children,
}) {
  return (
    <div className="wiz-command-bar">
      <div className="wiz-command-bar__row">
        <div className="wiz-command-bar__search">
          <Search size={15} className="wiz-command-bar__search-icon" aria-hidden />
          <input
            type="search"
            placeholder={searchPlaceholder}
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            aria-label={searchPlaceholder}
          />
        </div>
        {sortOptions.length > 0 && (
          <label className="wiz-command-bar__row" style={{ gap: '0.35rem' }}>
            <SlidersHorizontal size={14} aria-hidden />
            <select
              className="wiz-command-select"
              value={sort}
              onChange={(e) => onSortChange(e.target.value)}
              aria-label="Sort by"
            >
              {sortOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </label>
        )}
        {children}
      </div>
      {chips.length > 0 && (
        <div className="wiz-filter-chips" role="group" aria-label="Quick filters">
          {chips.map((chip) => (
            <button
              key={chip.id}
              type="button"
              className={`wiz-filter-chip${chip.active ? ' wiz-filter-chip--active' : ''}`}
              onClick={chip.onClick}
              aria-pressed={chip.active}
            >
              {chip.label}
              {typeof chip.count === 'number' && (
                <span className="wiz-filter-chip__count">{chip.count}</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
