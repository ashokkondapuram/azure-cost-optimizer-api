import React from 'react';
import { Layers } from 'lucide-react';
import { OPTIMIZATION_GROUP_BY } from '../../utils/optimizationGrouping';

export default function OptimizationGroupByToggle({
  value,
  onChange,
  className = '',
  showFlat = true,
}) {
  const options = showFlat
    ? OPTIMIZATION_GROUP_BY
    : OPTIMIZATION_GROUP_BY.filter((o) => o.id !== 'flat');

  return (
    <div className={`opt-group-by-toggle${className ? ` ${className}` : ''}`} role="group" aria-label="Group by">
      <span className="opt-group-by-toggle__label">
        <Layers size={13} aria-hidden />
        Group by
      </span>
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          className={`btn btn-ghost btn-sm${value === option.id ? ' active' : ''}`}
          onClick={() => onChange(option.id)}
          aria-pressed={value === option.id}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
