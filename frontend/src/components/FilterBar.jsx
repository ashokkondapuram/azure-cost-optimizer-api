import React from 'react';
import { Search, X, Filter } from 'lucide-react';
import FormInput from './forms/FormInput';
import FormCheckbox from './forms/FormCheckbox';

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
            <FormInput
              type="search"
              hideLabel
              label={search.placeholder || 'Search'}
              value={search.value}
              onChange={(e) => search.onChange(e.target.value)}
              placeholder={search.placeholder || 'Search…'}
              inputClassName="filter-bar__search-input"
            />
          </div>
        )}

        {selects.length > 0 && (
          <span className="filter-bar__divider" aria-hidden />
        )}

        {selects.map((sel) => {
          const hasAllOption = sel.options.some((opt) => opt.value === '');
          const options = hasAllOption
            ? sel.options
            : [{ value: '', label: sel.allLabel || `All ${sel.label.toLowerCase()}` }, ...sel.options];

          return (
            <label key={sel.id} className="filter-bar__field">
              <span className="filter-bar__label text-label">
                <Filter size={12} aria-hidden />
                {sel.label}
              </span>
              <select
                className="form-input"
                value={sel.value}
                onChange={(e) => sel.onChange(e.target.value)}
                aria-label={sel.label}
              >
                {options.map((opt) => (
                  <option key={opt.value || '__all__'} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </label>
          );
        })}

        {toggles.map((tog) => (
          <FormCheckbox
            key={tog.id}
            id={tog.id}
            label={tog.label}
            checked={tog.checked}
            onChange={(e) => tog.onChange(e.target.checked)}
            className="filter-bar__toggle"
          />
        ))}
      </div>

      <div className="filter-bar__meta">
        {resultCount != null && (
          <span className="filter-bar__count text-caption">
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
