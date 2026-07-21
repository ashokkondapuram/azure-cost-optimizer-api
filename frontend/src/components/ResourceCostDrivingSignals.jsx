import React, { useMemo } from 'react';
import { metricTimespanLabel } from '../utils/metricsTimespanUtils';
import {
  countCostDrivers,
  countCostSignalTriggers,
  filterMetricsBundleForCostSignals,
} from '../utils/costSignalsFilters';
import MetricsTriggersPanel from './MetricsTriggersPanel';
import CostDriverMappingPanel from './CostDriverMappingPanel';
import ResourceMetricsTimespanFilter from './ResourceMetricsTimespanFilter';
import { DrawerSectionSkeleton } from './DrawerBodySkeleton';

export default function ResourceCostDrivingSignals({
  resourceId,
  enabled = true,
  metricsData = null,
  metricsLoading = false,
  timespan,
  onTimespanChange,
  bare = false,
}) {
  const data = useMemo(
    () => (metricsData ? filterMetricsBundleForCostSignals(metricsData) : null),
    [metricsData],
  );
  const driverCount = data ? countCostDrivers(data) : 0;
  const triggerCount = data ? countCostSignalTriggers(data) : 0;

  if (!enabled || !resourceId) return null;
  if (metricsLoading) {
    return <DrawerSectionSkeleton rows={3} />;
  }
  if (!metricsData) return null;

  if (!data.ok && driverCount === 0 && triggerCount === 0) return null;

  const periodLabel = metricTimespanLabel(timespan || data?.timespan);
  const hasTriggers = triggerCount > 0;
  const hasDrivers = driverCount > 0;

  const signalsBody = (
    <div className="insight-drawer__cost-signals-grid">
      {hasTriggers && (
        <div className="insight-drawer__property-group insight-drawer__cost-signals-col">
          <h4 className="insight-drawer__property-group-title">Metric triggers</h4>
          <MetricsTriggersPanel
            metrics={data.metrics || []}
            derived={data.derived || []}
            compact
          />
        </div>
      )}
      {hasDrivers && (
        <div className="insight-drawer__property-group insight-drawer__cost-signals-col">
          <h4 className="insight-drawer__property-group-title">Cost drivers</h4>
          <CostDriverMappingPanel mapping={data.cost_driver_mapping} compact />
        </div>
      )}
    </div>
  );

  const header = (
    <div className="insight-drawer__cost-signals-head">
      <h4 className="insight-drawer__property-group-title">
        {bare ? `Cost signals · ${periodLabel}` : `Cost-driving signals · ${periodLabel}`}
      </h4>
      {timespan && onTimespanChange && (
        <ResourceMetricsTimespanFilter
          id="cost-driving-metrics-timespan"
          value={timespan}
          onChange={onTimespanChange}
        />
      )}
    </div>
  );

  if (bare) {
    if (!hasDrivers && !hasTriggers) return null;

    return (
      <div className="insight-drawer__cost-signals insight-drawer__cost-signals--compact">
        {(hasDrivers || hasTriggers) && (
          <div className="insight-drawer__kpi-strip insight-drawer__kpi-strip--compact insight-drawer__cost-signals-kpis">
            {hasDrivers && (
              <div className="insight-drawer__kpi">
                <span className="insight-drawer__kpi-label">Cost drivers</span>
                <span className="insight-drawer__kpi-value">{driverCount}</span>
              </div>
            )}
            {hasTriggers && (
              <div className="insight-drawer__kpi">
                <span className="insight-drawer__kpi-label">Triggers</span>
                <span className="insight-drawer__kpi-value">{triggerCount}</span>
              </div>
            )}
          </div>
        )}
        {header}
        {signalsBody}
      </div>
    );
  }

  return (
    <div className="insight-drawer__cost-signals">
      {header}
      {signalsBody}
    </div>
  );
}
