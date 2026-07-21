import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight } from 'lucide-react';
import { fetchVmSizing } from '../api/azure';
import { getErrorMessage } from '../api/errors';
import { formatCurrency } from '../utils/format';
import { metricTimespanLabel } from '../utils/metricsTimespanUtils';
import usePersistedMetricTimespan from '../hooks/usePersistedMetricTimespan';
import ResourceMetricsTimespanFilter from './ResourceMetricsTimespanFilter';

const VM_SIZING_TIMESPAN_KEY = 'finops-vmsizing-metrics-timespan';

function actionLabel(action) {
  if (action === 'downgrade') return 'Downsize';
  if (action === 'upgrade') return 'Upsize';
  if (action === 'cross_family') return 'Change family';
  return 'Review';
}

function formatMoney(value, currency = 'CAD') {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return formatCurrency(Number(value), { currency });
}

export default function VmSizingInsight({
  subscription,
  resourceGroup,
  vmName,
  enabled = true,
  data: dataProp,
  hideRecommendation = false,
  currency = 'CAD',
  timespan: timespanProp,
  onTimespanChange: onTimespanChangeProp,
}) {
  const [internalTimespan, internalOnTimespanChange] = usePersistedMetricTimespan(VM_SIZING_TIMESPAN_KEY);
  const timespan = timespanProp ?? internalTimespan;
  const onTimespanChange = onTimespanChangeProp ?? internalOnTimespanChange;

  const { data: fetchedData, isLoading, isError, error } = useQuery({
    queryKey: ['vm-sizing', subscription, resourceGroup, vmName, timespan],
    queryFn: () => fetchVmSizing({
      subscription_id: subscription,
      resource_group: resourceGroup,
      vm_name: vmName,
      timespan,
    }),
    enabled: enabled && !!subscription && !!resourceGroup && !!vmName && !dataProp,
    staleTime: 5 * 60_000,
  });
  const data = dataProp ?? fetchedData;
  const loading = !dataProp && isLoading;
  const periodLabel = metricTimespanLabel(timespan || data?.timespan);

  if (!enabled || !subscription || !resourceGroup || !vmName) return null;

  return (
    <div className="vm-sizing-insight">
      <div className="vm-sizing-insight__header">
        <span className="vm-sizing-insight__period-label">Metrics · {periodLabel}</span>
        <ResourceMetricsTimespanFilter
          id="vm-sizing-metrics-timespan"
          value={timespan}
          onChange={onTimespanChange}
        />
      </div>
      {loading && <p className="text-muted" style={{ fontSize: '0.85rem' }}>Loading CPU and memory metrics…</p>}
      {!loading && isError && (
        <p className="text-muted" style={{ fontSize: '0.85rem' }}>
          {getErrorMessage(error, 'Could not load VM metrics.')}
        </p>
      )}
      {data && (
        <>
          <dl className="insight-drawer__meta insight-drawer__meta--compact">
            {data.sku_profile?.family_label && (
              <>
                <dt>Family</dt>
                <dd>{data.sku_profile.family_label} ({data.sku_profile.family})</dd>
              </>
            )}
            {data.sku_profile?.vcpus != null && (
              <>
                <dt>Capacity</dt>
                <dd>{data.sku_profile.vcpus} vCPU · {data.sku_profile.memory_gb} GB</dd>
              </>
            )}
            {data.utilization?.avg_cpu_pct != null && (
              <>
                <dt>Average CPU utilization</dt>
                <dd>{data.utilization.avg_cpu_pct.toFixed(1)}%</dd>
              </>
            )}
            {data.utilization?.avg_memory_pct != null && (
              <>
                <dt>Average memory utilization</dt>
                <dd>{data.utilization.avg_memory_pct.toFixed(1)}%</dd>
              </>
            )}
          </dl>
          {!hideRecommendation && data.recommendation?.suggested_sku ? (
            <div className="vm-sizing-rec">
              <span className="vm-sizing-rec__action">{actionLabel(data.recommendation.action)}</span>
              <span className="vm-sizing-rec__path">
                {data.current_sku}
                <ArrowRight size={12} />
                {data.recommendation.suggested_sku}
              </span>
              {data.pricing?.pricing_status === 'available' && (
                <dl className="insight-drawer__meta insight-drawer__meta--compact" style={{ marginTop: 8 }}>
                  <dt>Current SKU (list price)</dt>
                  <dd>{formatMoney(data.pricing.current_sku_monthly_usd, currency)}/mo</dd>
                  <dt>Suggested SKU (list price)</dt>
                  <dd>{formatMoney(data.pricing.suggested_sku_monthly_usd, currency)}/mo</dd>
                  <dt>Est. savings</dt>
                  <dd>{formatMoney(data.pricing.estimated_monthly_savings_usd, currency)}/mo</dd>
                </dl>
              )}
              {data.pricing?.pricing_status === 'unavailable' && (
                <p className="text-muted" style={{ fontSize: '0.8rem', margin: '6px 0 0' }}>
                  Azure retail pricing unavailable for this SKU pair in this region.
                </p>
              )}
              {data.pricing?.pricing_source === 'azure_retail_prices' && (
                <p className="text-muted" style={{ fontSize: '0.75rem', margin: '4px 0 0' }}>
                  List/on-demand prices from Azure. Your bill may differ with discounts or reservations.
                </p>
              )}
              {data.recommendation.reasons?.[0] && (
                <p className="vm-sizing-rec__reason">{data.recommendation.reasons[0]}</p>
              )}
            </div>
          ) : !hideRecommendation ? (
            <p className="text-muted" style={{ fontSize: '0.85rem', margin: 0 }}>
              {data.recommendation?.action === 'insufficient_data'
                ? 'Metrics are not available yet for sizing.'
                : 'Current SKU matches observed utilization.'}
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}
