import React, { useMemo } from 'react';
import {
  buildSparklineGeometry,
  formatIsoCurrency,
  sparklineFromCosts,
  trendBadgeLabel,
} from '../../utils/costExplorerV2Utils';

function MiniSparkline({ geometry, stroke = '#4db8ff' }) {
  if (!geometry) return null;
  return (
    <svg className="ce-kpi-spark" viewBox="0 0 120 28" preserveAspectRatio="none" aria-hidden="true">
      <path
        d={geometry.linePath}
        fill="none"
        stroke={stroke}
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function HeroSparkline({ dailyPoints }) {
  const geometry = useMemo(
    () => buildSparklineGeometry(dailyPoints, 320, 56, 10),
    [dailyPoints],
  );

  if (!geometry) {
    return (
      <div className="sparkline sparkline--empty" aria-hidden="true">
        <span className="sparkline__placeholder">No daily cost data</span>
      </div>
    );
  }

  return (
    <svg className="sparkline animated" viewBox="0 0 320 56" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id="ce-spark-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#0073ff" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#0073ff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path className="sparkline__fill" d={geometry.fillPath} fill="url(#ce-spark-fill)" />
      <path
        className="sparkline__line"
        pathLength="1"
        d={geometry.linePath}
        fill="none"
        stroke="#4db8ff"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle className="sparkline__dot" cx={geometry.lastPoint.x} cy={geometry.lastPoint.y} r="3.5" fill="#4db8ff" />
    </svg>
  );
}

export default function CostExplorerHeroGrid({
  currency,
  spendLabel,
  total,
  periodDelta,
  compareTotal,
  comparePeriodLabel,
  projectedMonthEnd,
  avgDaily,
  daysElapsed,
  cumulativeTotal,
  rangeLabel,
  dailyPoints,
  compareDailyPoints,
  loading,
  showYoy,
  yoyPct,
  yoyPriorTotal,
  yoyYear,
  isPartialPeriod,
}) {
  const priorSpark = useMemo(
    () => sparklineFromCosts((compareDailyPoints || []).map((p) => p.cost), 120, 28),
    [compareDailyPoints],
  );
  const forecastSpark = useMemo(
    () => sparklineFromCosts((dailyPoints || []).map((p) => p.cost), 120, 28),
    [dailyPoints],
  );
  const avgSpark = useMemo(
    () => sparklineFromCosts((dailyPoints || []).map((p) => p.cost), 120, 28),
    [dailyPoints],
  );
  const cumulativeSpark = useMemo(() => {
    let running = 0;
    const costs = (dailyPoints || []).map((p) => {
      running += p.cost || 0;
      return running;
    });
    return sparklineFromCosts(costs, 120, 28);
  }, [dailyPoints]);

  const trendLabel = trendBadgeLabel(periodDelta, currency);
  const priorPct = compareTotal > 0 ? ((total - compareTotal) / compareTotal) * 100 : null;

  if (loading) {
    return (
      <div className="ce-hero-grid" aria-busy="true">
        <div className="bento-hero bento-hero--solo ce-hero-main panel" style={{ minHeight: 200 }} />
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="kpi kpi--glass ce-kpi ce-kpi--spark panel" style={{ minHeight: 120 }} />
        ))}
      </div>
    );
  }

  return (
    <div className="ce-hero-grid">
      <div className="bento-hero bento-hero--solo ce-hero-main">
        <div className="bento-hero__glow" aria-hidden="true" />
        <div className="bento-hero__content">
          <div className="label">{spendLabel} spend</div>
          <div className="value">{formatIsoCurrency(total, currency)}</div>
          <div className="sub">
            {daysElapsed ? `${daysElapsed} billing days` : 'Selected period'}
            {rangeLabel ? ` · ${rangeLabel}` : ''}
          </div>
          {trendLabel && (
            <div className={`trend-badge ${periodDelta < 0 ? 'trend-badge--positive' : 'trend-badge--negative'}`} id="ce-trend-badge">
              {trendLabel}
            </div>
          )}
          {showYoy && yoyPct != null && (
            <div className="ce-yoy-badge" id="ce-yoy-badge">
              <span className="ce-yoy-badge__label">vs same period last year</span>
              <strong id="ce-yoy-value">
                {yoyPct >= 0 ? '+' : ''}
                {yoyPct.toFixed(1)}%
              </strong>
              {yoyPriorTotal != null && (
                <span id="ce-yoy-prior">
                  {formatIsoCurrency(yoyPriorTotal, currency, { decimals: 0 })}
                  {yoyYear ? ` in ${yoyYear}` : ''}
                </span>
              )}
            </div>
          )}
        </div>
        <HeroSparkline dailyPoints={dailyPoints} />
      </div>

      <div className="kpi kpi--glass ce-kpi ce-kpi--spark">
        <div className="ce-kpi__head">
          <div className="label">vs prior period</div>
          <div className={`value${
            priorPct != null && priorPct < 0
              ? ' value--success'
              : priorPct != null && priorPct > 0
                ? ' value--warning'
                : ''
          }`} id="ce-kpi-prior-value">
            {priorPct != null ? `${priorPct >= 0 ? '+' : ''}${priorPct.toFixed(1)}%` : '—'}
          </div>
          <div className="sub">
            {compareTotal != null
              ? `${formatIsoCurrency(compareTotal, currency, { decimals: 0 })}${comparePeriodLabel ? ` · ${comparePeriodLabel}` : ''}`
              : 'No comparison data'}
          </div>
        </div>
        <MiniSparkline geometry={priorSpark} stroke="#34d399" />
      </div>

      <div className="kpi kpi--glass ce-kpi ce-kpi--spark">
        <div className="ce-kpi__head">
          <div className="label">Forecast / run rate</div>
          <div className="value">
            {projectedMonthEnd != null
              ? formatIsoCurrency(projectedMonthEnd, currency, { decimals: 0 })
              : '—'}
          </div>
          <div className="sub">Projected month-end at current pace</div>
        </div>
        <MiniSparkline geometry={forecastSpark} stroke="#4db8ff" />
      </div>

      <div className="kpi kpi--glass ce-kpi ce-kpi--spark">
        <div className="ce-kpi__head">
          <div className="label">Avg daily spend</div>
          <div className="value">
            {avgDaily != null ? formatIsoCurrency(avgDaily, currency, { decimals: 0 }) : '—'}
          </div>
          <div className="sub">
            {daysElapsed ? `Based on ${daysElapsed} billed days` : 'Selected period'}
          </div>
        </div>
        <MiniSparkline geometry={avgSpark} stroke="#a78bfa" />
      </div>

      <div className="kpi kpi--glass ce-kpi ce-kpi--spark ce-kpi--cumulative">
        <div className="ce-kpi__head">
          <div className="label">Cumulative spend</div>
          <div className="value">{formatIsoCurrency(cumulativeTotal ?? total, currency)}</div>
          <div className="sub" id="ce-kpi-cumulative-sub">
            {(isPartialPeriod ? 'Running total' : 'Period total')}
            {rangeLabel ? ` · ${rangeLabel}` : ''}
          </div>
        </div>
        <MiniSparkline geometry={cumulativeSpark} stroke="#4db8ff" />
      </div>
    </div>
  );
}
