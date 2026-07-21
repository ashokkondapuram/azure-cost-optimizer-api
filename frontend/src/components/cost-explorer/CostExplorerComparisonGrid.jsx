import React, { useMemo, useState } from 'react';
import { formatIsoCurrency, formatCompactCost } from '../../utils/costExplorerV2Utils';
import { buildPopSvg } from '../../utils/ceChartUtils';

function LegendToggle({ series, label, swatchClass, active, onToggle }) {
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

function PopChart({ dailyChart, compareDailyChart, loading, hidden }) {
  const svg = useMemo(
    () => buildPopSvg(dailyChart || [], compareDailyChart || []),
    [dailyChart, compareDailyChart],
  );

  if (loading) return <p className="panel-empty">Loading period comparison…</p>;
  if (!svg) return <p className="panel-empty">No daily data for period-over-period comparison.</p>;

  return (
    <div className="ce-pop-chart">
      <svg className="ce-pop-svg" viewBox="0 0 640 160" preserveAspectRatio="none">
        {[40, 80, 120].map((y) => (
          <line key={y} x1="0" y1={y} x2="640" y2={y} className="ce-trend-grid" />
        ))}
        {!hidden.prior && svg.priorPath && (
          <path
            className="ce-pop-line ce-pop-line--prior"
            d={svg.priorPath}
            fill="none"
            stroke="#64748b"
            strokeWidth="2"
            strokeLinecap="round"
            opacity="0.7"
          />
        )}
        {!hidden.current && (
          <path
            className="ce-pop-line ce-pop-line--current"
            d={svg.currentPath}
            fill="none"
            stroke="#4db8ff"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
        )}
      </svg>
      <div className="ce-trend-labels">
        {svg.labels.map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>
    </div>
  );
}

function MomChart({ momBars, currency }) {
  if (!momBars?.length) {
    return <p className="panel-empty">No monthly data for month-over-month view.</p>;
  }
  return (
    <div className="ce-mom-chart">
      <div className="ce-mom-bars">
        {momBars.map((bar) => (
          <div
            key={bar.key}
            className={`ce-mom-bar-group${bar.isCurrent ? ' ce-mom-bar-group--current' : ''}`}
            tabIndex={0}
            role="button"
            aria-label={`${bar.label} spend ${currency} ${bar.compact}`}
          >
            <span
              className={`ce-mom-bar${bar.isCurrent ? ' ce-mom-bar--current' : ''}`}
              style={{ '--h': `${bar.heightPct}%` }}
              title={formatIsoCurrency(bar.total, currency, { decimals: 0 })}
            />
            <span className="ce-mom-label">{bar.label}</span>
            <span className="ce-mom-value">{bar.compact}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ServiceCompare({ services, currency, loading, hidden }) {
  if (loading) return <p className="panel-empty">Loading service comparison…</p>;
  const top = (services || []).slice(0, 5);
  if (!top.length) {
    return <p className="panel-empty">No service comparison data for these periods.</p>;
  }
  const maxVal = Math.max(...top.map((r) => Math.max(r.current_cost, r.compare_cost)), 1);

  return (
    <div className="ce-svc-compare">
      {top.map((row) => (
        <div key={row.service} className="ce-svc-row" tabIndex={0} role="button">
          <span className="ce-svc-name" title={row.service}>
            {row.service.length > 12 ? `${row.service.slice(0, 11)}…` : row.service}
          </span>
          <div className="ce-svc-bars">
            {!hidden.prior && (
              <span
                className="ce-svc-bar ce-svc-bar--prior"
                style={{ width: `${(row.compare_cost / maxVal) * 100}%` }}
              />
            )}
            {!hidden.current && (
              <span
                className="ce-svc-bar ce-svc-bar--current"
                style={{ width: `${(row.current_cost / maxVal) * 100}%` }}
              />
            )}
          </div>
          <span className="ce-svc-vals">
            <span>{formatCompactCost(row.current_cost)}</span>
            <span className="muted">{formatCompactCost(row.compare_cost)}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

function YtdMonthly({ stacks, currency, show }) {
  if (!show) return null;
  if (!stacks?.length) {
    return <p className="panel-empty">No YTD monthly breakdown available.</p>;
  }
  return (
    <>
      <div className="ce-ytd-monthly">
        {stacks.map((month) => (
          <div
            key={month.key}
            className={`ce-ytd-month-group${month.isCurrent ? ' ce-ytd-month-group--current' : ''}`}
          >
            <div className="ce-ytd-month-stack">
              {month.segments.map((seg) => (
                <span
                  key={seg.key}
                  className={`ce-ytd-seg ce-ytd-seg--${seg.className}`}
                  style={{ '--h': `${seg.heightPct}%` }}
                  title={`${seg.key}: ${formatIsoCurrency(seg.cost, currency, { decimals: 0 })}`}
                />
              ))}
            </div>
            <span className="ce-ytd-month-label">{month.label}</span>
            <span className="ce-ytd-month-total">{month.compact}</span>
          </div>
        ))}
      </div>
      <div className="ce-ytd-legend">
        <span className="ce-legend-item" data-series="compute">
          <span className="ce-ytd-legend-dot" style={{ '--c': '#60a5fa' }} />
          Compute
        </span>
        <span className="ce-legend-item" data-series="db">
          <span className="ce-ytd-legend-dot" style={{ '--c': '#f87171' }} />
          Databases
        </span>
        <span className="ce-legend-item" data-series="storage">
          <span className="ce-ytd-legend-dot" style={{ '--c': '#fbbf24' }} />
          Storage
        </span>
        <span className="ce-legend-item" data-series="other">
          <span className="ce-ytd-legend-dot" style={{ '--c': '#94a3b8' }} />
          Other
        </span>
      </div>
    </>
  );
}

export default function CostExplorerComparisonGrid({
  dailyChart,
  compareDailyChart,
  momBars,
  comparisonServices,
  ytdStacks,
  currency,
  comparePeriodLabel,
  showYtd,
  loading,
}) {
  const [popHidden, setPopHidden] = useState({});
  const [svcHidden, setSvcHidden] = useState({});

  const togglePop = (key) => setPopHidden((prev) => ({ ...prev, [key]: !prev[key] }));
  const toggleSvc = (key) => setSvcHidden((prev) => ({ ...prev, [key]: !prev[key] }));

  return (
    <div className="ce-comparison-grid">
      <div className="panel ce-comparison-panel">
        <div className="panel-head panel-head--split">
          <div>
            <h2 className="section-title section-title--bar">Period-over-period</h2>
            <p className="panel-sub">Current vs previous period overlay</p>
          </div>
          <div className="ce-chart-legend ce-chart-legend--inline">
            <LegendToggle
              series="current"
              label="Current"
              swatchClass="ce-legend-swatch--current"
              active={!popHidden.current}
              onToggle={() => togglePop('current')}
            />
            <LegendToggle
              series="prior"
              label={comparePeriodLabel || 'Previous'}
              swatchClass="ce-legend-swatch--prior"
              active={!popHidden.prior}
              onToggle={() => togglePop('prior')}
            />
          </div>
        </div>
        <PopChart
          dailyChart={dailyChart}
          compareDailyChart={compareDailyChart}
          loading={loading}
          hidden={popHidden}
        />
      </div>

      <div className="panel ce-comparison-panel">
        <div className="panel-head panel-head--split">
          <div>
            <h2 className="section-title section-title--bar">Month-over-month</h2>
            <p className="panel-sub">Last 6 months</p>
          </div>
        </div>
        <MomChart momBars={momBars} currency={currency} />
      </div>

      <div className="panel ce-comparison-panel ce-comparison-panel--wide">
        <div className="panel-head panel-head--split">
          <div>
            <h2 className="section-title section-title--bar">Service spend comparison</h2>
            <p className="panel-sub">Top 5 services · current vs prior period</p>
          </div>
          <div className="ce-chart-legend ce-chart-legend--inline">
            <LegendToggle
              series="current"
              label="Current"
              swatchClass="ce-legend-swatch--current"
              active={!svcHidden.current}
              onToggle={() => toggleSvc('current')}
            />
            <LegendToggle
              series="prior"
              label="Prior"
              swatchClass="ce-legend-swatch--prior"
              active={!svcHidden.prior}
              onToggle={() => toggleSvc('prior')}
            />
          </div>
        </div>
        <ServiceCompare
          services={comparisonServices}
          currency={currency}
          loading={loading}
          hidden={svcHidden}
        />
      </div>

      {showYtd && (
        <div className="panel ce-comparison-panel ce-comparison-panel--ytd">
          <div className="panel-head panel-head--split">
            <div>
              <h2 className="section-title section-title--bar">YTD monthly spend</h2>
              <p className="panel-sub">Grouped by month</p>
            </div>
          </div>
          <YtdMonthly stacks={ytdStacks} currency={currency} show={showYtd} />
        </div>
      )}
    </div>
  );
}
