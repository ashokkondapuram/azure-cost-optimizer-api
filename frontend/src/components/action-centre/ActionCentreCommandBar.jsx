import React from 'react';
import {
  DEFAULT_AC_FILTERS,
  SOURCE_CHIP_LABELS,
  WORKFLOW_CHIP_LABELS,
  TYPE_CHIP_LABELS,
  acHasActiveFilters,
} from '../../utils/actionCentreV2Utils';

const SEVERITY_CHIPS = [
  { value: 'all', label: 'Any severity' },
  { value: 'critical', label: 'Critical', className: 'ac-chip--critical' },
  { value: 'high', label: 'High', className: 'ac-chip--high' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}

function ChipGroup({ group, chips, filters, onFilter }) {
  return (
    <div className="ac-chip-group" data-chip-group={group}>
      {chips.map((chip) => (
        <button
          key={chip.value}
          type="button"
          className={`ac-chip${filters[group] === chip.value ? ' active' : ''}${chip.className ? ` ${chip.className}` : ''}`}
          data-chip={group}
          data-value={chip.value}
          onClick={() => onFilter(group, chip.value)}
        >
          {chip.label}
        </button>
      ))}
    </div>
  );
}

export default function ActionCentreCommandBar({
  filters = DEFAULT_AC_FILTERS,
  onFilter,
  onSearch,
  onClear,
  visibleCount = 0,
  totalCount = 0,
}) {
  const hasFilters = acHasActiveFilters(filters);
  const filterNote = hasFilters
    ? `Showing ${visibleCount} of ${totalCount} findings`
    : `Showing all ${visibleCount} findings · ${totalCount} total in queue`;

  const workflowChips = [
    { value: 'all', label: 'All' },
    ...Object.entries(WORKFLOW_CHIP_LABELS).map(([value, label]) => ({ value, label })),
  ];
  const sourceChips = [
    { value: 'all', label: 'Any source' },
    ...Object.entries(SOURCE_CHIP_LABELS).map(([value, label]) => ({
      value,
      label,
      className: `ac-chip--${value}`,
    })),
  ];
  const typeChips = [
    { value: 'all', label: 'All types' },
    ...Object.entries(TYPE_CHIP_LABELS).map(([value, label]) => ({ value, label })),
  ];

  return (
    <div className="ac-command" id="ac-command">
      <div className="ac-command__row">
        <div className="search-wrap ac-command__search">
          <SearchIcon />
          <input
            type="search"
            className="search"
            id="ac-search"
            placeholder="Search resources or recommendations"
            aria-label="Search findings"
            value={filters.search || ''}
            onChange={(e) => onSearch(e.target.value)}
          />
        </div>
        {hasFilters && (
          <button type="button" className="ac-command__clear link link--sm" onClick={onClear}>
            Clear filters
          </button>
        )}
      </div>
      <div className="ac-chip-bar" id="ac-chip-bar" role="toolbar" aria-label="Filter findings">
        <ChipGroup group="workflow" chips={workflowChips} filters={filters} onFilter={onFilter} />
        <span className="ac-chip-divider" aria-hidden="true" />
        <ChipGroup group="severity" chips={SEVERITY_CHIPS} filters={filters} onFilter={onFilter} />
        <span className="ac-chip-divider" aria-hidden="true" />
        <ChipGroup group="source" chips={sourceChips} filters={filters} onFilter={onFilter} />
        <span className="ac-chip-divider" aria-hidden="true" />
        <ChipGroup group="type" chips={typeChips} filters={filters} onFilter={onFilter} />
      </div>
      <p className="ac-filter-note" aria-live="polite">{filterNote}</p>
    </div>
  );
}
