import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Layers, ChevronDown } from 'lucide-react';
import { fetchResourceTypes } from '../api/azure';
import {
  normalizeResourceTypeSelection,
  resourceTypeFilterSummary,
  selectCategoryTypes,
  toggleTypeSelection,
} from '../utils/resourceTypeFilter';

export default function ResourceTypeFilter({
  selected = [],
  onChange,
  className = '',
}) {
  const { data: catalog, isLoading } = useQuery({
    queryKey: ['resource-types-catalog'],
    queryFn: fetchResourceTypes,
    staleTime: 24 * 60 * 60_000,
  });

  const summary = useMemo(
    () => resourceTypeFilterSummary(selected, catalog),
    [selected, catalog],
  );

  const emitChange = (next) => {
    onChange?.(normalizeResourceTypeSelection(next, catalog));
  };

  return (
    <div className={`resource-type-filter${className ? ` ${className}` : ''}`}>
      <details className="resource-type-filter__details">
        <summary className="resource-type-filter__trigger">
          <Layers size={14} aria-hidden />
          <span>
            {summary ? `Types: ${summary}` : 'All resource types'}
          </span>
          <ChevronDown size={14} className="resource-type-filter__chevron" aria-hidden />
        </summary>
        <div className="resource-type-filter__panel">
          <div className="resource-type-filter__actions">
            <button
              type="button"
              className="btn btn-ghost btn-xs"
              onClick={() => emitChange([])}
              disabled={isLoading}
            >
              All types
            </button>
            {selected.length > 0 && (
              <span className="resource-type-filter__count">
                {selected.length} selected
              </span>
            )}
          </div>
          {isLoading && <p className="resource-type-filter__loading">Loading types…</p>}
          {!isLoading && (catalog?.categories || []).map((group) => (
            <div key={group.category} className="resource-type-filter__group">
              <div className="resource-type-filter__group-head">
                <span className="resource-type-filter__group-title">{group.category}</span>
                <button
                  type="button"
                  className="btn btn-ghost btn-xs"
                  onClick={() => emitChange(
                    selectCategoryTypes(selected, group.types, true),
                  )}
                >
                  All
                </button>
              </div>
              <ul className="resource-type-filter__list">
                {group.types.map((row) => {
                  const checked = selected.includes(row.canonical);
                  return (
                    <li key={row.canonical}>
                      <label className="resource-type-filter__option">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => emitChange(
                            toggleTypeSelection(selected, row.canonical),
                          )}
                        />
                        <span>{row.label}</span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}
