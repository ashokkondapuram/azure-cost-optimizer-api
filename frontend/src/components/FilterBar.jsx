import React from 'react';
import { Search, X, Filter } from 'lucide-react';

/**
 * Unified filter toolbar for list pages.
 *
 * @param {object} props
 * @param {{ value: string, onChange: (v: string) => void, placeholder?: string }} [props.search]
 * @param {{ id: string, label: string, value: string, onChange: (v: string) => void, options: { value: string, label: string }[] }[]} [props.selects]
 * @param {{ id: string, label: string, checked: boolean, onChange: (v: boolean) => void }[]} [props.toggles]
 * @param {() => void} [props.onClear]
 * @param {{ shown: number, total?: number, label?: string }} [props.resultCount]
 */
export default function FilterBar({
  search,
  selects = [],
  toggles = [],
  onClear,
  resultCount,
  className = '',
}) {
  return (
    <div className={`filter-bar${className ? ` ${className}` : ''}`}>
      <div className="filter-bar__primary">
        {search && (
          <div className="filter-bar__search search-field">
            <Search size={14} aria-hidden />
            <input
              type="search"
              value={search.value}
              onChange={(e) => search.onChange(e.target.value)}
              placeholder={search.placeholder || 'Search…'}
              aria-label={search.placeholder || 'Search'}
            />
          </div>
        )}

        {selects.length > 0 && (
          <span className="filter-bar__divider" aria-hidden />
        )}

        {selects.map((sel) => (
          <label key={sel.id} className="filter-bar__field">
            <span className="filter-bar__label">
              <Filter size={12} aria-hidden />
              {sel.label}
            </span>
            <select
              value={sel.value}
              onChange={(e) => sel.onChange(e.target.value)}
              aria-label={sel.label}
            >
              {sel.options.map((opt) => (
                <option key={opt.value || '__all__'} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </label>
        ))}

        {toggles.map((tog) => (
          <label key={tog.id} className="filter-bar__toggle checkbox-label">
            <input
              type="checkbox"
              checked={tog.checked}
              onChange={(e) => tog.onChange(e.target.checked)}
            />
            {tog.label}
          </label>
        ))}
      </div>

      <div className="filter-bar__meta">
        {resultCount != null && (
          <span className="filter-bar__count">
            {resultCount.shown.toLocaleString()}
            {resultCount.total != null && resultCount.total !== resultCount.shown
              ? ` of ${resultCount.total.toLocaleString()}`
              : ''}
            {' '}
            {resultCount.label || 'results'}
          </span>
        )}
        {onClear && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClear}>
            <X size={13} aria-hidden />
            Clear filters
          </button>
        )}
      </div>
    </div>
  );
}
