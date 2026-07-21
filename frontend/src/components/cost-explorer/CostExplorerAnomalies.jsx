import React from 'react';
import { formatIsoCurrency, trendClass, trendPctLabel } from '../../utils/costExplorerV2Utils';

function DailyAnomalyCard({ anomaly, currency, onViewBreakdown }) {
  const delta = anomaly.delta ?? anomaly.deviation;
  const direction = delta > 0 ? 'up' : 'down';
  const warn = anomaly.severity === 'high' || Math.abs(anomaly.z_score || 0) >= 2;
  return (
    <li
      className={`ce-anomaly-card${warn ? ' ce-anomaly-card--warn' : ''}`}
      tabIndex={0}
      data-ce-anomaly="daily"
    >
      <span className={`ce-anomaly-card__icon${warn ? '' : ' ce-anomaly-card__icon--info'}`} aria-hidden="true">
        {direction === 'up' ? '↑' : '↓'}
      </span>
      <div>
        <strong>
          Daily spend {direction === 'up' ? 'spike' : 'drop'} on {anomaly.date}
        </strong>
        <p>
          Spend was {anomaly.z_score?.toFixed?.(1) ?? '—'}σ from the rolling baseline
          {anomaly.baseline != null ? ` (baseline ${formatIsoCurrency(anomaly.baseline, currency, { decimals: 0 })})` : ''}.
        </p>
        {delta != null && (
          <span className="ce-anomaly-card__meta">
            {direction === 'up' ? 'Increased' : 'Decreased'} {formatIsoCurrency(Math.abs(delta), currency, { decimals: 0 })} vs baseline
          </span>
        )}
        <button type="button" className="ce-anomaly-action" onClick={onViewBreakdown}>
          View breakdown
        </button>
      </div>
    </li>
  );
}

function ServiceAnomalyCard({ anomaly, currency, onViewBreakdown }) {
  const serviceName = anomaly.service_name || anomaly.service || 'Service';
  return (
    <li className="ce-anomaly-card" tabIndex={0} data-ce-anomaly={serviceName}>
      <span className="ce-anomaly-card__icon ce-anomaly-card__icon--info" aria-hidden="true">◎</span>
      <div>
        <strong>{serviceName} spend anomaly</strong>
        <p>{anomaly.message || `Unusual spend pattern detected for ${serviceName}.`}</p>
        {anomaly.delta != null && (
          <span className="ce-anomaly-card__meta">
            Spend changed {formatIsoCurrency(Math.abs(anomaly.delta), currency, { decimals: 0 })}
          </span>
        )}
        <button type="button" className="ce-anomaly-action" onClick={onViewBreakdown}>
          View breakdown
        </button>
      </div>
    </li>
  );
}

function SpendVelocity({ velocity, currency }) {
  if (!velocity) return null;
  return (
    <div className="side-card ce-side-card">
      <h3 className="section-title section-title--bar">Spend velocity</h3>
      <div className="ce-velocity">
        <div className="ce-velocity__row">
          <span>This week</span>
          <strong>{formatIsoCurrency(velocity.thisWeek, currency, { decimals: 0 })}</strong>
          {velocity.thisWeekPct != null && (
            <span className={`ce-trend ${trendClass(velocity.thisWeekPct)}`}>
              {trendPctLabel(velocity.thisWeekPct)}
            </span>
          )}
        </div>
        <div className="ce-velocity__row">
          <span>Last week</span>
          <strong>{formatIsoCurrency(velocity.lastWeek, currency, { decimals: 0 })}</strong>
          {velocity.lastWeekPct != null && (
            <span className={`ce-trend ${trendClass(velocity.lastWeekPct)}`}>
              {trendPctLabel(velocity.lastWeekPct)}
            </span>
          )}
        </div>
        <div className="ce-velocity__row">
          <span>Daily peak</span>
          <strong>{formatIsoCurrency(velocity.peakCost, currency, { decimals: 0 })}</strong>
          <span className="ce-trend ce-trend--muted">{velocity.peakLabel}</span>
        </div>
      </div>
    </div>
  );
}

export default function CostExplorerAnomalies({
  dailyAnomalies,
  serviceAnomalies,
  velocity,
  currency,
  loading,
  onViewBreakdown,
}) {
  const daily = (dailyAnomalies?.anomalies || []).slice(0, 3);
  const service = (serviceAnomalies?.service_anomalies || []).slice(0, 2);
  const hasAny = daily.length > 0 || service.length > 0;

  return (
    <aside className="ce-side" aria-label="Spend patterns">
      <div className="panel ce-anomaly-panel">
        <div className="panel-head panel-head--inset">
          <h2 className="section-title section-title--bar">Cost anomalies</h2>
        </div>
        {loading ? (
          <p className="panel-empty">Loading anomalies…</p>
        ) : !hasAny ? (
          <p className="panel-empty">No cost anomalies detected in the recent window.</p>
        ) : (
          <ul className="ce-anomaly-list">
            {daily.map((a) => (
              <DailyAnomalyCard
                key={`${a.date}-${a.total}`}
                anomaly={a}
                currency={currency}
                onViewBreakdown={onViewBreakdown}
              />
            ))}
            {service.map((a) => (
              <ServiceAnomalyCard
                key={a.service_name || a.service}
                anomaly={a}
                currency={currency}
                onViewBreakdown={onViewBreakdown}
              />
            ))}
          </ul>
        )}
      </div>
      <SpendVelocity velocity={velocity} currency={currency} />
    </aside>
  );
}
