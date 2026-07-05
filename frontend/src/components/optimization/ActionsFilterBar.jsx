import React from 'react';

export default function ActionsFilterBar({
  statusFilter,
  onStatusChange,
  actionTypeFilter,
  onActionTypeFilter,
  resourceTypeFilter,
  onResourceTypeFilter,
  statusOptions = [],
  actionTypeOptions = [],
  resourceTypeOptions = [],
}) {
  return (
    <div className="actions-filter-bar">
      <div className="filter-row">

        <div className="filter-control">
          <label htmlFor="status-filter" className="filter-label">Status</label>
          <select
            id="status-filter"
            className="filter-select"
            value={statusFilter}
            onChange={(e) => onStatusChange(e.target.value)}
          >
            <option value="">All statuses</option>
            {statusOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        <div className="filter-control">
          <label htmlFor="action-type-filter" className="filter-label">Action type</label>
          <select
            id="action-type-filter"
            className="filter-select"
            value={actionTypeFilter}
            onChange={(e) => onActionTypeFilter(e.target.value)}
          >
            <option value="">All types</option>
            {actionTypeOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        <div className="filter-control">
          <label htmlFor="resource-type-filter" className="filter-label">Resource type</label>
          <select
            id="resource-type-filter"
            className="filter-select"
            value={resourceTypeFilter}
            onChange={(e) => onResourceTypeFilter(e.target.value)}
          >
            <option value="">All types</option>
            {resourceTypeOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
