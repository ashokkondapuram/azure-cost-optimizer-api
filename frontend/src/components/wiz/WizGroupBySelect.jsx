import React from 'react';
import { WIZ_RESOURCE_GROUP_BY_OPTIONS } from '../../utils/taxonomy';

export default function WizGroupBySelect({
  value = '',
  onChange,
  className = 'wiz-command-select',
  id = 'wiz-group-by',
}) {
  return (
    <select
      id={id}
      className={className}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      aria-label="Group by"
    >
      {WIZ_RESOURCE_GROUP_BY_OPTIONS.map((option) => (
        <option key={option.value || 'none'} value={option.value}>
          {option.value ? `Group by ${option.label.toLowerCase()}` : option.label}
        </option>
      ))}
    </select>
  );
}
