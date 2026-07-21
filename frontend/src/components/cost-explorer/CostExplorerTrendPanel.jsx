import React, { useMemo, useState } from 'react';
import { formatIsoCurrency } from '../../utils/costExplorerV2Utils';
import {
  buildCumulativeSvg,
  buildDailyTrendSvg,
} from '../../utils/ceChartUtils';

const MODES = [
  { id: 'daily', label: 'Daily spend' },
  { id: 'cumulative', label: 'Cumulative' },
  { id: 'forecast', label: 'Forecast' },
];

function LegendItem({ series, label, swatchClass, active, onToggle }) {
  if (onToggle) {
    return (
      <button
        type="button"
        className={`ce-legend-item ce-legend-item--toggle${active ? '' : ' ce-legend-item--off'}`}
        data-series={series}
        onClick={onToggle}
        aria-pressed={active}
      >
        <span className={`ce-legend-swatch ${swatchClass}`} />
        {label}
      </button>
    );
  }
  return (
    <span className="ce-legend-item" data-series={series}>
      <span className={`ce-legend-swatch ${swatchClass}`} />
      {label}
    </span>
  );
}

export default function CostExplorerTrendPanel({
  dailyChart,
  cumulativeChart,
  compareDailyChart,
  forecastPoints,
  currency,
  rangeLabel,
  avgDaily,
  comparePeriodLabel,
  loading,
  isMtd,
}) {
  const [mode, setMode] = useState('daily');
  const [hiddenSeries, setHiddenSeries] = useState({});

  const dailyPoints = useMemo(
    () => (dailyChart || []).map((row) => ({
      date: row.date,
      dateLabel: row.dateLabel,
      cost: row.cost ?? 0,
    })),
    [dailyChart],
  );

  const comparePoints = useMemo(
    () => (compareDailyChart || cumulativeChart || []).map((row) => ({
      date: row.date,
      dateLabel: row.dateLabel,
      cost: row.cost ?? 0,
    })),
    [compareDailyChart, cumulativeChart],
  );

  const hasForecast = isMtd && forecastPoints?.length > 0;
  const activeModes = hasForecast ? MODES : MODES.filter((m) => m.id !== 'forecast');
  const effectiveMode = mode === 'forecast' && !hasForecast ? 'daily' : mode;

  const dailySvg = useMemo(
    () => buildDailyTrendSvg(
      dailyPoints,
      effectiveMode === 'forecast' ? forecastPoints : [],
    ),
    [dailyPoints, forecastPoints, effectiveMode],
  );

  const cumulativeSvg = useMemo(
    () => buildCumulativeSvg(dailyPoints, comparePoints),
    [dailyPoints, comparePoints],
  );

  const sub = rangeLabel
    ? `${rangeLabel}${avgDaily != null ? ` · Avg ${formatIsoCurrency(avgDaily, currency, { decimals: 0 })}/day` : ''}`
    : null;

  const title = useMemo(() => {
    if (effectiveMode === 'cumulative') return 'Cumulative cost';
    if (effectiveMode === 'forecast') return 'Spend forecast';
    return hasForecast ? 'Spend trend with forecast' : 'Daily spend trend';
  }, [effectiveMode, hasForecast]);

  const toggleSeries = (key) => {
    setHiddenSeries((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const legend = useMemo(() => {
    if (effectiveMode === 'cumulative') {
      return (
        <>
          <LegendItem series="current" label="Actual cumulative" swatchClass="ce-legend-swatch--current" />
          <LegendItem
            series="prior"
            label={comparePeriodLabel || 'Previous period'}
            swatchClass="ce-legend-swatch--prior"
            active={!hiddenSeries.prior}
            onToggle={() => toggleSeries('prior')}
          />
        </>
      );
    }
    if (effectiveMode === 'forecast' || hasForecast) {
      return (
        <>
          <LegendItem
            series="current"
            label="Actual"
            swatchClass="ce-legend-swatch--current"
            active={!hiddenSeries.current}
            onToggle={() => toggleSeries('current')}
          />
          <LegendItem
            series="forecast"
            label="Forecast"
            swatchClass="ce-legend-swatch--forecast"
            active={!hiddenSeries.forecast}
            onToggle={() => toggleSeries('forecast')}
          />
        </>
      );
    }
    return (
      <LegendItem series="current" label="Daily spend" swatchClass="ce-legend-swatch--current" />
    );
  }, [effectiveMode, hasForecast, comparePeriodLabel, hiddenSeries]);

  const dimmed = effectiveMode === 'forecast';
  const showForecastLine = hasForecast && (effectiveMode === 'daily' || effectiveMode === 'forecast');

  return (
    <div className="panel ce-trend-panel ce-trend-panel--primary">
      <div className="panel-head panel-head--split ce-trend-panel-head">
        <div>
          <h2 className="section-title section-title--bar">{title}</h2>
          {sub && <p className="panel-sub">{sub}</p>}
        </div>
        <div className="ce-trend-head-actions">
          <div className="ce-chart-mode" role="group" aria-label="Chart mode">
            {activeModes.map((m) => (
              <button
                key={m.id}
                type="button"
                className={`ce-chart-mode-btn${effectiveMode === m.id ? ' active' : ''}`}
                data-ce-chart-mode={m.id}
                onClick={() => setMode(m.id)}
              >
                {m.label}
              </button>
            ))}
          </div>
          <div className="ce-chart-legend ce-chart-legend--inline">
            {legend}
          </div>
        </div>
      </div>

      {loading ? (
        <p className="panel-empty">Loading spend trend…</p>
      ) : !dailyPoints.length ? (
        <p className="panel-empty">No cost data for this period. Sync costs to populate the chart.</p>
      ) : effectiveMode === 'cumulative' && cumulativeSvg ? (
        <div className="ce-trend-chart ce-trend-chart--cumulative" data-ce-chart-view="cumulative">
          <div className="ce-cumulative-yaxis" aria-hidden="true">
            {cumulativeSvg.yTicks.slice().reverse().map((tick) => (
              <span key={tick.label}>{tick.label}</span>
            ))}
          </div>
          <svg className="ce-trend-svg ce-cumulative-svg" viewBox="0 0 640 200" preserveAspectRatio="none">
            <defs>
              <linearGradient id="ce-cumulative-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#0073ff" stopOpacity="0.22" />
                <stop offset="100%" stopColor="#0073ff" stopOpacity="0" />
              </linearGradient>
            </defs>
            {[40, 80, 120, 160].map((y) => (
              <line key={y} x1="0" y1={y} x2="640" y2={y} className="ce-trend-grid" />
            ))}
            {!hiddenSeries.prior && cumulativeSvg.priorPath && (
              <path
                className="ce-cumulative-line ce-cumulative-line--prior"
                d={cumulativeSvg.priorPath}
                fill="none"
                stroke="#64748b"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                opacity="0.75"
              />
            )}
            {!hiddenSeries.current && (
              <>
                <path className="ce-cumulative-area" d={cumulativeSvg.areaPath} fill="url(#ce-cumulative-fill)" />
                <path
                  className="ce-cumulative-line ce-cumulative-line--current"
                  d={cumulativeSvg.linePath}
                  fill="none"
                  stroke="#4db8ff"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <circle
                  className="ce-trend-dot"
                  cx={cumulativeSvg.dot.x}
                  cy={cumulativeSvg.dot.y}
                  r="4"
                  fill="#4db8ff"
                />
              </>
            )}
          </svg>
          <div className="ce-trend-labels">
            {cumulativeSvg.labels.map((label) => (
              <span key={label}>{label}</span>
            ))}
          </div>
        </div>
      ) : dailySvg ? (
        <div className="ce-trend-chart ce-trend-chart--primary" data-ce-chart-view="daily">
          <svg className="ce-trend-svg" viewBox="0 0 640 200" preserveAspectRatio="none">
            <defs>
              <linearGradient id="ce-trend-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#0073ff" stopOpacity="0.28" />
                <stop offset="100%" stopColor="#0073ff" stopOpacity="0" />
              </linearGradient>
            </defs>
            {[50, 100, 150].map((y) => (
              <line key={y} x1="0" y1={y} x2="640" y2={y} className="ce-trend-grid" />
            ))}
            {showForecastLine && dailySvg.dividerX != null && (
              <line
                className="ce-trend-forecast-divider"
                x1={dailySvg.dividerX}
                y1="20"
                x2={dailySvg.dividerX}
                y2="185"
                strokeDasharray="4 4"
              />
            )}
            {!hiddenSeries.current && (
              <>
                <path
                  className={`ce-trend-area${dimmed ? ' ce-trend-area--dimmed' : ''}`}
                  d={dailySvg.areaPath}
                  fill="url(#ce-trend-fill)"
                />
                <path
                  className={`ce-trend-line${dimmed ? ' ce-trend-line--dimmed' : ''}`}
                  d={dailySvg.linePath}
                  fill="none"
                  stroke="#4db8ff"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <circle
                  className="ce-trend-dot"
                  cx={dailySvg.dot.x}
                  cy={dailySvg.dot.y}
                  r="4"
                  fill="#4db8ff"
                />
              </>
            )}
            {showForecastLine && dailySvg.forecastPath && !hiddenSeries.forecast && (
              <path
                className={`ce-trend-forecast${effectiveMode === 'forecast' ? ' ce-trend-forecast--emphasis' : ''}`}
                d={dailySvg.forecastPath}
                fill="none"
                stroke="#fbbf24"
                strokeWidth="2"
                strokeDasharray="6 4"
                strokeLinecap="round"
              />
            )}
          </svg>
          <div className="ce-trend-labels">
            {dailySvg.labels.map((label, i) => (
              <span
                key={`${label}-${i}`}
                className={i === dailySvg.labels.length - 1 && hasForecast ? 'ce-trend-label--forecast' : undefined}
              >
                {label}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
