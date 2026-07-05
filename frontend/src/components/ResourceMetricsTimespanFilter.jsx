import React from 'react';
import { METRIC_TIMESPAN_OPTIONS } from '../utils/metricsTimespanUtils';

function stopHeaderToggle(event) {
  event.stopPropagation();
}

export default function ResourceMetricsTimespanFilter({
  value,
  onChange,
  className = '',
  id = 'resource-metrics-timespan',
}) {
  return (
    <label
      className={`resource-metrics-timespan${className ? ` ${className}` : ''}`}
      htmlFor={id}
      onClick={stopHeaderToggle}
      onMouseDown={stopHeaderToggle}
    >
      <span className="resource-metrics-timespan__label">Period</span>
      <select
        id={id}
        className="select-field resource-metrics-timespan__select"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-label="Metrics time period"
      >
        {METRIC_TIMESPAN_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
