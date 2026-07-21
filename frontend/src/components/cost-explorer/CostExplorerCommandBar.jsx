import React from 'react';

const CHIP_OPTIONS = [
  { id: 'all', label: 'All spend' },
  { id: 'increasing', label: 'Increasing', dotClass: 'ce-chip__dot--up' },
  { id: 'anomaly', label: 'Spend anomaly', dotClass: 'ce-chip__dot--warn' },
  { id: 'top10', label: 'Top 10 only' },
];

export default function CostExplorerCommandBar({
  search,
  onSearchChange,
  serviceFilter,
  onServiceFilterChange,
  services,
  resourceGroupFilter,
  onResourceGroupFilterChange,
  resourceGroups,
  tagFilter,
  onTagFilterChange,
  tags,
  chipFilter,
  onChipFilterChange,
}) {
  return (
    <div className="command-bar command-bar--v2 ce-command-bar">
      <div className="command-bar__row">
        <div className="search-wrap">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16" aria-hidden="true">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <input
            type="search"
            className="search"
            placeholder="Search resources or services"
            aria-label="Search spend"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
          />
        </div>
        <select
          className="filter"
          aria-label="Service"
          value={serviceFilter}
          onChange={(e) => onServiceFilterChange(e.target.value)}
        >
          <option value="all">All services</option>
          {(services || []).map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <select
          className="filter"
          aria-label="Resource group"
          value={resourceGroupFilter}
          onChange={(e) => onResourceGroupFilterChange(e.target.value)}
        >
          <option value="all">All resource groups</option>
          {(resourceGroups || []).map((rg) => (
            <option key={rg} value={rg}>{rg}</option>
          ))}
        </select>
        <select
          className="filter"
          aria-label="Tag"
          value={tagFilter}
          onChange={(e) => onTagFilterChange(e.target.value)}
        >
          <option value="all">All tags</option>
          {(tags || []).map((tag) => (
            <option key={tag.value} value={tag.value}>{tag.label}</option>
          ))}
        </select>
      </div>
      <div className="command-bar__chips" role="group" aria-label="Spend filters">
        {CHIP_OPTIONS.map((chip) => (
          <button
            key={chip.id}
            type="button"
            className={`ce-chip${chipFilter === chip.id ? ' active' : ''}`}
            data-ce-chip={chip.id}
            onClick={() => onChipFilterChange(chip.id)}
          >
            {chip.dotClass && <span className={`ce-chip__dot ${chip.dotClass}`} />}
            {chip.label}
          </button>
        ))}
      </div>
    </div>
  );
}
