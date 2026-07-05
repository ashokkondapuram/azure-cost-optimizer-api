import React from 'react';
import { metricTimespanLabel } from '../utils/metricsTimespanUtils';
import MetricsTriggersPanel from './MetricsTriggersPanel';
import CostDriverMappingPanel from './CostDriverMappingPanel';
import DrawerCollapsibleSection from './DrawerCollapsibleSection';
import ResourceMetricsTimespanFilter from './ResourceMetricsTimespanFilter';
import { DrawerSectionSkeleton } from './DrawerBodySkeleton';

export default function ResourceCostDrivingSignals({
  resourceId,
  enabled = true,
  metricsData = null,
  metricsLoading = false,
  timespan,
  onTimespanChange,
}) {
  if (!enabled || !resourceId) return null;
  if (metricsLoading) {
    return <DrawerSectionSkeleton rows={3} />;
  }
  if (!metricsData) return null;

  const data = metricsData;
  const driverCount = data?.cost_driver_mapping?.cost_drivers?.length || 0;
  const triggerCount = [...(data?.metrics || []), ...(data?.derived || [])].filter((m) => m?.trigger).length;

  if (!data.ok && driverCount === 0 && triggerCount === 0) return null;

  const periodLabel = metricTimespanLabel(timespan || data?.timespan);

  return (
    <DrawerCollapsibleSection
      title={`Cost-driving signals · ${periodLabel}`}
      variant="info"
      defaultOpen={false}
      compact
      badge={driverCount || triggerCount}
      hint="Expand to see inventory properties and metrics used for cost recommendations."
      headerAction={timespan && onTimespanChange ? (
        <ResourceMetricsTimespanFilter
          id="cost-driving-metrics-timespan"
          value={timespan}
          onChange={onTimespanChange}
        />
      ) : null}
    >
      <MetricsTriggersPanel
        metrics={data.metrics || []}
        derived={data.derived || []}
      />
      <CostDriverMappingPanel mapping={data.cost_driver_mapping} compact />
    </DrawerCollapsibleSection>
  );
}
