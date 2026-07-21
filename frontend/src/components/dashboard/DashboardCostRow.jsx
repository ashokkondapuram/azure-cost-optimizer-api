import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  buildSparklineGeometry,
  formatIsoCurrency,
} from '../../utils/dashboardV2Utils';
import { formatDateRange } from '../../utils/format';

function DashboardSparkline({ dailyPoints, gradientId = 'dashboard-spark-fill' }) {
  const geometry = useMemo(
    () => buildSparklineGeometry(dailyPoints),
    [dailyPoints],
  );

  if (!geometry) {
    return (
      <div className="sparkline sparkline--empty" aria-hidden="true">
        <span className="sparkline__placeholder">No daily cost data</span>
      </div>
    );
  }

  const { linePath, fillPath, lastPoint } = geometry;

  return (
    <svg className="sparkline animated" viewBox="0 0 320 56" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#0073ff" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#0073ff" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path className="sparkline__fill" d={fillPath} fill={`url(#${gradientId})`} />
      <path
        className="sparkline__line"
        pathLength="1"
        d={linePath}
        fill="none"
        stroke="#4db8ff"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle
        className="sparkline__dot"
        cx={lastPoint.x}
        cy={lastPoint.y}
        r="3.5"
        fill="#4db8ff"
        style={{ transformOrigin: `${lastPoint.x}px ${lastPoint.y}px` }}
      />
    </svg>
  );
}

export default function DashboardCostRow({
  currency,
  spendLabel = 'Month to date',
  mtdAmount,
  periodStart,
  periodEnd,
  projectedMonthly,
  mtdDelta,
  weeklyAvg,
  potentialSavings,
  savingsPct,
  dailyPoints,
}) {
  const dateRangeLabel = periodStart && periodEnd
    ? formatDateRange(periodStart, periodEnd)
    : null;

  const projectedLabel = projectedMonthly > 0
    ? `On track for ${formatIsoCurrency(projectedMonthly, currency, { decimals: 0 })} this month`
    : null;

  const trendLabel = mtdDelta != null && mtdDelta !== 0
    ? `${mtdDelta < 0 ? '↓' : '↑'} ${formatIsoCurrency(Math.abs(mtdDelta), currency, { decimals: 0 })} vs prior period`
    : null;

  const savingsSub = savingsPct != null && savingsPct > 0
    ? `~${savingsPct}% of month to date spend`
    : null;

  const subParts = [dateRangeLabel, projectedLabel].filter(Boolean);

  return (
    <div className="cost-row cost-row--enhanced">
      <div className="bento-hero bento-hero--solo">
        <div className="bento-hero__glow" aria-hidden="true" />
        <div className="bento-hero__content">
          <div className="label">{spendLabel} spend</div>
          <div className="value">{formatIsoCurrency(mtdAmount, currency)}</div>
          {subParts.length > 0 && (
            <div className="sub">{subParts.join(' · ')}</div>
          )}
          {trendLabel && (
            <div className={`trend-badge ${mtdDelta < 0 ? 'trend-badge--positive' : 'trend-badge--negative'}`}>
              {trendLabel}
            </div>
          )}
        </div>
        <DashboardSparkline dailyPoints={dailyPoints} />
      </div>
      <div className="cost-aside">
        <div className="kpi kpi--glass">
          <div className="label">Weekly avg spend</div>
          <div className="value">{formatIsoCurrency(weeklyAvg, currency, { decimals: 0 })}</div>
          <div className="sub">Rolling 7 days</div>
        </div>
        <Link className="kpi kpi--link" to="/action-centre?hasAction=1">
          <div className="label">Potential savings</div>
          <div className="value value--success">
            {formatIsoCurrency(potentialSavings, currency, { decimals: 0 })}
          </div>
          <div className="sub">{savingsSub || 'Based on open findings with savings estimates'}</div>
        </Link>
      </div>
    </div>
  );
}
