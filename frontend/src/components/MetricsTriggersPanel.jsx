import React from 'react';
import { optimizationMetricStatusLabel } from '../utils/resourceMetricsUtils';

function TriggerCard({ metric }) {
  const trigger = metric.trigger;
  if (!trigger) return null;

  return (
    <div className="metrics-triggers-panel__item">
      <div className="metrics-triggers-panel__header">
        <strong>{metric.label || metric.fact_key}</strong>
        {metric.status && (
          <span className={`resource-metrics-status resource-metrics-status--${metric.status}`}>
            {optimizationMetricStatusLabel(metric.status)}
          </span>
        )}
      </div>
      <p className="metrics-triggers-panel__threshold">
        Threshold: {trigger.threshold}
      </p>
      {trigger.effect_cost && (
        <p className="metrics-triggers-panel__effect">
          <strong>Cost:</strong> {trigger.effect_cost}
        </p>
      )}
      {trigger.effect_performance && (
        <p className="metrics-triggers-panel__effect">
          <strong>Performance:</strong> {trigger.effect_performance}
        </p>
      )}
      {trigger.safety_gate && (
        <p className="metrics-triggers-panel__gate text-muted">{trigger.safety_gate}</p>
      )}
    </div>
  );
}

export default function MetricsTriggersPanel({ metrics = [], derived = [], compact = false }) {
  const withTriggers = [...(metrics || []), ...(derived || [])].filter((m) => m?.trigger);
  if (!withTriggers.length) return null;

  return (
    <div className={`metrics-triggers-panel${compact ? ' metrics-triggers-panel--compact' : ''}`}>
      {!compact && (
        <>
          <h4 className="metrics-triggers-panel__title">What this means</h4>
          <p className="metrics-triggers-panel__hint text-muted">
            How these metrics relate to cost optimization and performance.
          </p>
        </>
      )}
      <div className="metrics-triggers-panel__grid">
        {withTriggers.map((metric) => (
          <TriggerCard key={metric.fact_key} metric={metric} />
        ))}
      </div>
    </div>
  );
}
