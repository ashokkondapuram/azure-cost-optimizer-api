import React, { useEffect, useState } from 'react';
import { CE_PRESETS } from '../../utils/costExplorerV2Utils';

export default function CostExplorerTimeFilter({
  timeframe,
  onTimeframeChange,
  granularity,
  onGranularityChange,
  customFrom,
  customTo,
  onCustomFromChange,
  onCustomToChange,
  rangeLabel,
}) {
  const [draftFrom, setDraftFrom] = useState(customFrom);
  const [draftTo, setDraftTo] = useState(customTo);

  useEffect(() => {
    setDraftFrom(customFrom);
    setDraftTo(customTo);
  }, [customFrom, customTo]);

  const activePreset = CE_PRESETS.find((p) => p.value === timeframe)?.key
    || (timeframe === 'Custom' ? 'custom' : null);

  const applyCustomRange = () => {
    onCustomFromChange(draftFrom);
    onCustomToChange(draftTo);
  };

  return (
    <div className="ce-time-filter-bar" role="region" aria-label="Time range">
      <div className="ce-time-filter-bar__row">
        <div className="ce-time-presets" role="group" aria-label="Preset period">
          {CE_PRESETS.map((preset) => (
            <button
              key={preset.key}
              type="button"
              className={`ce-time-preset${activePreset === preset.key ? ' active' : ''}`}
              onClick={() => onTimeframeChange(preset.value)}
            >
              {preset.label}
            </button>
          ))}
        </div>
        <div className="ce-time-filter-bar__controls">
          <div className="ce-granularity-toggle" role="group" aria-label="Granularity">
            <button
              type="button"
              className={`ce-granularity-btn${granularity === 'Daily' ? ' active' : ''}`}
              onClick={() => onGranularityChange('Daily')}
            >
              Daily
            </button>
            <button
              type="button"
              className={`ce-granularity-btn${granularity === 'Monthly' ? ' active' : ''}`}
              onClick={() => onGranularityChange('Monthly')}
            >
              Monthly
            </button>
          </div>
        </div>
      </div>
      {timeframe === 'Custom' && (
        <div className="ce-time-custom" id="ce-time-custom">
          <label className="ce-time-custom__label" htmlFor="ce-custom-start">Start</label>
          <input
            id="ce-custom-start"
            type="date"
            className="ce-time-custom__input"
            value={draftFrom}
            onChange={(e) => setDraftFrom(e.target.value)}
            aria-label="Custom start date"
          />
          <span className="ce-time-custom__sep" aria-hidden="true">–</span>
          <label className="ce-time-custom__label" htmlFor="ce-custom-end">End</label>
          <input
            id="ce-custom-end"
            type="date"
            className="ce-time-custom__input"
            value={draftTo}
            onChange={(e) => setDraftTo(e.target.value)}
            aria-label="Custom end date"
          />
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            id="ce-custom-apply"
            onClick={applyCustomRange}
          >
            Apply
          </button>
        </div>
      )}
      {rangeLabel && (
        <p className="ce-time-range-label" id="ce-period-range-label">{rangeLabel}</p>
      )}
    </div>
  );
}
