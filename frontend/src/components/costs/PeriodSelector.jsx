import React from 'react';
import { COST_TIMEFRAME_OPTIONS } from '../../config/costTimeframes';

export default function PeriodSelector({
  currentTimeframe,
  compareTimeframe,
  onCurrentChange,
  onCompareChange,
  currentFromDate,
  currentToDate,
  onCurrentFromChange,
  onCurrentToChange,
  compareFromDate,
  compareToDate,
  onCompareFromChange,
  onCompareToChange,
}) {
  return (
    <div className="cost-period-selector">
      <div className="cost-period-selector__group">
        <label className="cost-period-selector__label" htmlFor="current-period">Current period</label>
        <select
          id="current-period"
          className="input"
          value={currentTimeframe}
          onChange={(e) => onCurrentChange(e.target.value)}
        >
          {COST_TIMEFRAME_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        {currentTimeframe === 'Custom' && (
          <div className="cost-period-selector__dates">
            <input
              type="date"
              className="input"
              value={currentFromDate || ''}
              onChange={(e) => onCurrentFromChange(e.target.value)}
              aria-label="Current period start date"
            />
            <input
              type="date"
              className="input"
              value={currentToDate || ''}
              onChange={(e) => onCurrentToChange(e.target.value)}
              aria-label="Current period end date"
            />
          </div>
        )}
      </div>
      <div className="cost-period-selector__group">
        <label className="cost-period-selector__label" htmlFor="compare-period">Compare to</label>
        <select
          id="compare-period"
          className="input"
          value={compareTimeframe}
          onChange={(e) => onCompareChange(e.target.value)}
        >
          {COST_TIMEFRAME_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        {compareTimeframe === 'Custom' && (
          <div className="cost-period-selector__dates">
            <input
              type="date"
              className="input"
              value={compareFromDate || ''}
              onChange={(e) => onCompareFromChange(e.target.value)}
              aria-label="Compare period start date"
            />
            <input
              type="date"
              className="input"
              value={compareToDate || ''}
              onChange={(e) => onCompareToChange(e.target.value)}
              aria-label="Compare period end date"
            />
          </div>
        )}
      </div>
    </div>
  );
}
