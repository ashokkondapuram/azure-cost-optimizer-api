import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Activity } from 'lucide-react';
import { fetchResourceAzureMetrics } from '../api/azure';
import { getErrorMessage } from '../api/errors';
import { dataQualityMessage } from '../utils/resourceMetricsUtils';
import { metricTimespanLabel } from '../utils/metricsTimespanUtils';
import ResourceMetricsDetailTable from './ResourceMetricsDetailTable';
import ResourceInventoryProperties from './ResourceInventoryProperties';
import AzureMetricsLearnMoreLink from './AzureMetricsLearnMoreLink';
import ResourceMetricsTimespanFilter from './ResourceMetricsTimespanFilter';
import DrawerCollapsibleSection from './DrawerCollapsibleSection';
import { DrawerSectionSkeleton } from './DrawerBodySkeleton';

export default function ResourceAzureMetrics({
  resourceId,
  enabled = true,
  sectionTitle = 'Metrics and properties',
  timespan,
  onTimespanChange,
  prefetchedData = undefined,
  prefetchedLoading = false,
  prefetchedError = null,
}) {
  const usePrefetch = prefetchedData !== undefined || prefetchedLoading;
  const { data: queryData, isLoading: queryLoading, isError: queryError, error, isFetching } = useQuery({
    queryKey: ['resource-azure-metrics', resourceId, timespan],
    queryFn: () => fetchResourceAzureMetrics({ resource_id: resourceId, timespan }),
    enabled: enabled && !!resourceId && !!timespan && !usePrefetch,
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const data = usePrefetch ? prefetchedData : queryData;
  const isLoading = usePrefetch ? prefetchedLoading : queryLoading;
  const isError = usePrefetch ? !!prefetchedError : queryError;
  const loadError = usePrefetch ? prefetchedError : error;

  const inventoryProperties = data?.inventory_properties || [];
  const hasMonitorDetail = (data?.metrics?.length > 0)
    || (data?.derived?.length > 0)
    || (data?.metrics_detail?.length > 0)
    || (data?.instances?.length > 0);
  const hasContent = hasMonitorDetail || inventoryProperties.length > 0;

  const qualityMessage = data
    ? dataQualityMessage(data.data_quality, data.unavailable_reason || data.error)
    : null;

  if (!enabled || !resourceId) return null;

  const periodLabel = metricTimespanLabel(timespan || data?.timespan);
  const metricCount = (data?.metrics?.length || 0) + (data?.derived?.length || 0);
  const badge = metricCount > 0
    ? String(metricCount)
    : (inventoryProperties.length > 0 ? String(inventoryProperties.length) : null);

  const headerAction = (
    <div className="resource-metrics-header-actions">
      {timespan && onTimespanChange && (
        <ResourceMetricsTimespanFilter
          value={timespan}
          onChange={onTimespanChange}
        />
      )}
      {data?.doc_url || data?.doc_ref ? (
        <AzureMetricsLearnMoreLink
          docRef={data.doc_ref}
          docUrl={data.doc_url}
          displayName={data.display_name}
          compact
        />
      ) : null}
    </div>
  );

  return (
    <DrawerCollapsibleSection
      title={`${sectionTitle} · ${periodLabel}`}
      icon={<Activity size={13} />}
      defaultOpen
      compact
      badge={badge}
      headerAction={headerAction}
    >
      {data?.data_quality === 'cost_export_only' && data?.ok && (
        <p className="alert alert--info" role="status" style={{ fontSize: '0.85rem' }}>
          Usage estimated from cost data.
        </p>
      )}

      {data?.ok && data?.unavailable_reason && inventoryProperties.length > 0 && (
        <p className="alert alert--info" role="status" style={{ fontSize: '0.85rem' }}>
          Live Azure Monitor metrics are unavailable. Showing synced inventory properties instead.
        </p>
      )}

      {isLoading && <DrawerSectionSkeleton rows={4} />}

      {isError && (
        <p className="text-muted" style={{ fontSize: '0.85rem' }}>
          {getErrorMessage(loadError, 'Could not load metrics for this resource.')}
        </p>
      )}

      {data && !data.ok && !isLoading && (
        <p className="text-muted" style={{ fontSize: '0.85rem' }}>
          {qualityMessage || data.error || 'Metrics not available for this resource type.'}
        </p>
      )}

      {data?.ok && !hasContent && !isLoading && (
        <p className="text-muted" style={{ fontSize: '0.85rem', margin: 0 }}>
          No synced properties or metrics for this resource yet.
        </p>
      )}

      {data?.ok && hasContent && (
        <>
          {isFetching && !isLoading && (
            <p className="text-muted" style={{ fontSize: '0.78rem', margin: '0 0 0.5rem' }}>Refreshing…</p>
          )}

          <ResourceInventoryProperties properties={inventoryProperties} />

          {hasMonitorDetail && (
            <ResourceMetricsDetailTable
              metrics={data.metrics || []}
              derived={data.derived || []}
              metricsDetail={data.metrics_detail || []}
              instances={data.instances || []}
            />
          )}

          <div className="insight-drawer__metrics-source-row">
            <p className="insight-drawer__metrics-source text-muted">
              Source:{' '}
              {data.data_quality === 'cost_export_only' || data.data_quality === 'inventory+cost_export'
                ? 'Inventory and cost data'
                : data.data_quality === 'inventory'
                  ? 'Synced inventory'
                  : data.data_quality === 'azure_monitor+k8s_agent'
                    ? 'Azure Monitor and K8s agent'
                    : 'Azure Monitor'}
              {' · '}
              {periodLabel}
              {' · '}
              {data.display_name || data.canonical_type || 'resource'}
              {data.instances?.length > 0 && (
                ` · ${data.instances.length} ${data.instances[0]?.source === 'k8s_agent' ? 'node' : 'instance'}${data.instances.length === 1 ? '' : 's'}`
              )}
            </p>
            {(data.doc_url || data.doc_ref) && (
              <AzureMetricsLearnMoreLink
                docRef={data.doc_ref}
                docUrl={data.doc_url}
                displayName={data.display_name}
              />
            )}
          </div>
        </>
      )}
    </DrawerCollapsibleSection>
  );
}
