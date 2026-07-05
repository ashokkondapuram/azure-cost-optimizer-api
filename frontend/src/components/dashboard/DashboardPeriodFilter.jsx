import React from 'react';
import { DASHBOARD_COST_PERIOD_OPTIONS } from '../../utils/costTimespanUtils';

export default function DashboardPeriodFilter({ value, onChange, className = '' }) {
  return (
    <label className={`dashboard-period-filter${className ? ` ${className}` : ''}`}>
      <span className="dashboard-period-filter__label">Cost period</span>
      <select
        className="select-field dashboard-period-filter__select"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-label="Dashboard cost period"
      >
        {DASHBOARD_COST_PERIOD_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
