import React from 'react';

export default function GroupBySelect({
  value,
  onChange,
  options = [
    { value: 'none', label: 'No grouping' },
    { value: 'resource_group', label: 'Resource group' },
    { value: 'resource_type', label: 'Resource type' },
    { value: 'status', label: 'Status' },
    { value: 'tier', label: 'Tier' },
  ],
  label = 'Group by',
}) {
  return (
    <div className="filter-control">
      <label htmlFor="group-by" className="filter-label">{label}</label>
      <select
        id="group-by"
        className="filter-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map(opt => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
