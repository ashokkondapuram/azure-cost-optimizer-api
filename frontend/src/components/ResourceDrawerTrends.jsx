import React, { useMemo } from 'react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from 'recharts';
import { useQueries, useQuery } from '@tanstack/react-query';
import { fetchBatchResourceLookup, fetchUtilizationSeries } from '../api/azure';
import { getErrorMessage } from '../api/errors';
import { metricTimespanLabel } from '../utils/metricsTimespanUtils';
import ResourceMetricsTimespanFilter from './ResourceMetricsTimespanFilter';
import { DrawerSectionSkeleton } from './DrawerBodySkeleton';
import {
  resolveRelatedResources,
  metricValuesFromPayload,
} from '../utils/drawerRelatedResources';
import {
  resolveArmType,
  trendMetricKeysForResource,
  trendMetricKeysForType,
} from '../utils/drawerCapabilities';
import {
  insufficientTrendMessage,
  hasTrendSummaryMetrics,
  noTrendSummaryMetricsMessage,
  visibleTrendSummaryCards,
} from '../utils/drawerTrendMetrics';
import {
  buildMetricTrendChart,
  trendSummaryForMetric,
  extractSeriesPointsFromBundle,
  mergeTrendSeriesPoints,
  trendSummaryFromSeries,
  hasTrendMetricDataInBundle,
} from '../utils/drawerMetricTrendSeries';
import { drawerStaticMetricCards } from '../utils/drawerResourceTypeMetrics';
import { formatFactValue } from '../utils/resourceMetricsUtils';
import WizChartTooltip from './wiz/charts/WizChartTooltip';
import { chartAxisSuffix, formatChartAxisTick, formatChartMetricValue } from '../utils/formatMetricUnits';

function TrendSummaryCard({ label, value, detail, muted = false }) {
  if (!value) return null;
  return (
    <article className={`drawer-trends__summary-card${muted ? ' drawer-trends__summary-card--muted' : ''}`}>
      <span className="drawer-trends__summary-label">{label}</span>
      <strong className="drawer-trends__summary-value">{value}</strong>
      {detail && <p className="drawer-trends__summary-detail">{detail}</p>}
    </article>
  );
}

function MetricTrendLineChart({ data, title, unit = '', factKey = '' }) {
  if (!data?.length) return null;
  const axisUnit = chartAxisSuffix(factKey, unit);
  const tickFormatter = (value) => formatChartAxisTick(value, { factKey, unit });
  const tooltipFormatter = (raw, row) => row?.formattedValue || formatChartMetricValue(raw, { factKey, unit });
  return (
    <div className="wiz-chart-card drawer-trends__chart drawer-trends__chart--series">
      <h4 className="wiz-chart-card__title">{title}</h4>
      <div className="wiz-chart-body">
        <ResponsiveContainer width="100%" height={190}>
          <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border-subtle, #e5e7eb)" />
            <XAxis dataKey="dateLabel" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
            <YAxis tick={{ fontSize: 11 }} width={52} unit={axisUnit} tickFormatter={tickFormatter} />
            <Tooltip content={<WizChartTooltip valueFormatter={tooltipFormatter} />} />
            <Line
              type="monotone"
              dataKey="value"
              stroke="#0073ff"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, strokeWidth: 0 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function RelatedComparisonChart({ series, metricLabel, factKey = '', unit = '' }) {
  if (!series?.length || series.length < 2) return null;
  const axisUnit = chartAxisSuffix(factKey, unit);
  const tickFormatter = (value) => formatChartAxisTick(value, { factKey, unit });
  const tooltipFormatter = (raw) => formatChartMetricValue(raw, { factKey, unit });
  return (
    <div className="wiz-chart-card drawer-trends__chart drawer-trends__chart--comparison">
      <h4 className="wiz-chart-card__title">Related resources · {metricLabel}</h4>
      <p className="drawer-trends__chart-note">Current period snapshot comparison</p>
      <div className="wiz-chart-body">
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border-subtle, #e5e7eb)" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} width={52} unit={axisUnit} tickFormatter={tickFormatter} />
            <Tooltip content={<WizChartTooltip valueFormatter={tooltipFormatter} />} />
            <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} maxBarSize={40} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function analysisTrendForSpec(spec, trends) {
  if (!spec.analysisTrendKey || !trends) return null;
  return trends[spec.analysisTrendKey] ?? null;
}

export default function ResourceDrawerTrends({
  resource,
  resourceId,
  subscriptionId,
  apiPath = '',
  canonicalType = '',
  metricsData = null,
  analysisData = null,
  findings = [],
  timespan,
  onTimespanChange,
  loading = false,
}) {
  const armType = resolveArmType(resource);
  const metricKeys = useMemo(() => {
    const fromResource = trendMetricKeysForResource(resource, apiPath);
    if (fromResource.length) return fromResource;
    return trendMetricKeysForType(canonicalType, armType);
  }, [resource, apiPath, canonicalType, armType]);

  const relatedResources = useMemo(
    () => resolveRelatedResources(resource, {
      findings,
      dependencies: analysisData?.dependencies,
      inventoryProperties: metricsData?.inventory_properties,
    }),
    [resource, findings, analysisData?.dependencies, metricsData?.inventory_properties],
  );

  const relatedIds = useMemo(
    () => relatedResources.map((r) => r.id).filter(Boolean),
    [relatedResources],
  );

  const seriesQueries = useQueries({
    queries: metricKeys.map((spec) => ({
      queryKey: ['drawer-metric-series', subscriptionId, resourceId, spec.factKey, timespan],
      queryFn: ({ signal }) => fetchUtilizationSeries({
        subscription_id: subscriptionId,
        resource_id: resourceId,
        metric_name: spec.factKey,
        timespan,
      }, { signal }),
      enabled: Boolean(subscriptionId && resourceId && spec.factKey && !spec.static && timespan),
      staleTime: 5 * 60_000,
      retry: 1,
    })),
  });

  const metricSeriesCharts = useMemo(() => metricKeys.map((spec, index) => {
    const apiPoints = seriesQueries[index]?.data?.points || [];
    const bundlePoints = extractSeriesPointsFromBundle(metricsData, spec.factKey);
    const points = mergeTrendSeriesPoints(apiPoints, bundlePoints);
    return {
      spec,
      chartData: buildMetricTrendChart(points, { label: spec.label, unit: spec.unit, factKey: spec.factKey }),
      loading: seriesQueries[index]?.isLoading,
      pointCount: points.length,
      source: apiPoints.length >= 2 ? 'api' : (bundlePoints.length >= 2 ? 'bundle' : 'none'),
    };
  }), [metricKeys, seriesQueries, metricsData]);

  const { data: relatedBundle, isLoading: relatedLoading } = useQuery({
    queryKey: ['drawer-related-metrics', subscriptionId, relatedIds.join('|'), timespan],
    queryFn: ({ signal }) => fetchBatchResourceLookup({
      subscription_id: subscriptionId,
      resource_ids: relatedIds,
      timespan,
      include_metrics: true,
      include_advanced_analysis: false,
      profile: 'drawer',
    }, { signal }),
    enabled: Boolean(subscriptionId && relatedIds.length && timespan),
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const comparisonSeries = useMemo(() => {
    const primaryKey = metricKeys.find((spec) => !spec.static)?.factKey || metricKeys[0]?.factKey;
    if (!primaryKey) return [];

    const primaryValues = metricValuesFromPayload(metricsData, metricKeys);
    const primaryEntry = primaryValues[primaryKey];
    const series = [];

    if (primaryEntry) {
      series.push({
        name: 'This resource',
        value: primaryEntry.value,
        relation: 'Primary',
      });
    }

    if (relatedBundle?.items) {
      for (const rel of relatedResources) {
        const payload = relatedBundle.items[rel.id.toLowerCase()]?.metrics;
        const relValues = metricValuesFromPayload(payload, metricKeys);
        const relEntry = relValues[primaryKey];
        if (relEntry) {
          series.push({
            name: rel.label,
            value: relEntry.value,
            relation: rel.relation,
          });
        }
      }
    }

    return series;
  }, [metricsData, metricKeys, relatedBundle, relatedResources]);

  const trends = analysisData?.trends;
  const periodLabel = metricTimespanLabel(timespan || metricsData?.timespan);

  const summaryCards = useMemo(() => {
    const staticCards = drawerStaticMetricCards(resource, metricKeys, metricsData, {
      canonicalType,
      armType,
    });
    if (staticCards.length) return staticCards;

    return metricKeys
      .filter((spec) => !spec.static)
      .map((spec, index) => {
        const trendPayload = analysisTrendForSpec(spec, trends);
        const summary = trendSummaryForMetric(trendPayload, spec.label, spec.factKey);
        if (summary) return summary;

        const query = seriesQueries[index];
        const apiPoints = query?.data?.points || [];
        const bundlePoints = extractSeriesPointsFromBundle(metricsData, spec.factKey);
        const mergedPoints = mergeTrendSeriesPoints(apiPoints, bundlePoints);

        if (mergedPoints.length >= 2) {
          const fromSeries = trendSummaryFromSeries(mergedPoints, spec.label, spec.factKey, periodLabel);
          if (fromSeries) return fromSeries;
        }

        const currentEntry = metricValuesFromPayload(metricsData, [spec])[spec.factKey];
        if (currentEntry) {
          return {
            label: spec.label,
            value: formatFactValue(spec.factKey, currentEntry.value),
            detail: `Current period · ${periodLabel}`,
          };
        }

        if (query?.isLoading) return null;

        return {
          label: spec.label,
          value: 'Insufficient data',
          detail: insufficientTrendMessage(spec.label),
          muted: true,
        };
      })
      .filter(Boolean);
  }, [metricKeys, trends, resource, metricsData, canonicalType, armType, seriesQueries, periodLabel]);

  const chartEntries = metricSeriesCharts.filter((entry) => entry.chartData.length >= 2);
  const chartedFactKeys = chartEntries.map((entry) => entry.spec.factKey);
  const visibleSummaryCards = visibleTrendSummaryCards(summaryCards, metricKeys, chartedFactKeys);

  const seriesLoading = seriesQueries.some((q) => q.isLoading);
  const seriesError = seriesQueries.find((q) => q.isError)?.error || null;
  const seriesErrorMessage = seriesError
    ? getErrorMessage(seriesError, 'Could not load utilization trends from Azure Monitor.')
    : null;
  const hasSeriesCharts = chartEntries.length > 0;
  const hasSummaries = visibleSummaryCards.length > 0;
  const hasComparison = comparisonSeries.length >= 2;
  const hasBundleTrendData = hasTrendMetricDataInBundle(metricsData, metricKeys);

  if (loading && !metricsData && !analysisData) {
    return <DrawerSectionSkeleton rows={4} />;
  }

  const hasConfiguredMetrics = hasTrendSummaryMetrics(canonicalType, armType);
  const primaryMetricLabel = metricKeys.find((spec) => !spec.static)?.label || metricKeys[0]?.label;
  const emptyMessage = !hasConfiguredMetrics
    ? noTrendSummaryMetricsMessage()
    : hasBundleTrendData
      ? `Need at least two daily data points to chart ${primaryMetricLabel || 'this metric'}. Try a longer lookback window or wait for more Azure Monitor samples.`
      : `No trend data yet for ${primaryMetricLabel || 'this resource'}. Sync Azure Monitor metrics to populate utilization trends.`;

  if (!hasConfiguredMetrics && !hasComparison && !relatedResources.length) {
    return (
      <p className="insight-drawer__empty insight-drawer__empty--compact">
        {noTrendSummaryMetricsMessage()}
      </p>
    );
  }

  if (seriesLoading && !hasSeriesCharts && !hasSummaries && !hasBundleTrendData) {
    return <DrawerSectionSkeleton rows={4} />;
  }

  if (!hasSeriesCharts && !hasSummaries && !hasComparison && !relatedResources.length) {
    return (
      <p className="insight-drawer__empty insight-drawer__empty--compact">
        {emptyMessage}
      </p>
    );
  }

  const chartsBody = (
    <div className="drawer-trends__chart-grid">
      {chartEntries.map(({ spec, chartData }) => (
        <MetricTrendLineChart
          key={spec.factKey}
          data={chartData}
          title={`${spec.label} over time`}
          unit={spec.unit}
          factKey={spec.factKey}
        />
      ))}
    </div>
  );

  return (
    <div className="drawer-trends">
      <div className="drawer-trends__head">
        <span className="drawer-trends__period">Trend window · {periodLabel}</span>
        {timespan && onTimespanChange && (
          <ResourceMetricsTimespanFilter
            id="drawer-trends-timespan"
            value={timespan}
            onChange={onTimespanChange}
          />
        )}
      </div>

      {seriesErrorMessage && !hasSeriesCharts && (
        <p className="alert alert--warning" role="status" style={{ fontSize: '0.85rem' }}>
          {seriesErrorMessage}
        </p>
      )}

      {hasSummaries && (
        <section className="insight-drawer__property-group drawer-trends__summary-section">
          <h4 className="insight-drawer__property-group-title">Trend summary</h4>
          <div className="drawer-trends__summary-grid">
            {visibleSummaryCards.map((card) => (
              <TrendSummaryCard key={card.label} {...card} />
            ))}
          </div>
        </section>
      )}

      {seriesLoading && !hasSeriesCharts && (
        <DrawerSectionSkeleton rows={3} />
      )}

      {hasSeriesCharts && (
        <section className="insight-drawer__property-group drawer-trends__charts-section">
          <h4 className="insight-drawer__property-group-title">Utilization over time</h4>
          {chartsBody}
        </section>
      )}

      {relatedLoading && relatedIds.length > 0 && (
        <DrawerSectionSkeleton rows={2} />
      )}

      {!relatedLoading && hasComparison && (
        <section className="insight-drawer__property-group drawer-trends__comparison-section">
          <h4 className="insight-drawer__property-group-title">Peer comparison</h4>
          <RelatedComparisonChart
            series={comparisonSeries}
            metricLabel={metricKeys.find((spec) => !spec.static)?.label || 'Primary metric'}
            factKey={metricKeys.find((spec) => !spec.static)?.factKey || metricKeys[0]?.factKey}
            unit={metricKeys.find((spec) => !spec.static)?.unit || metricKeys[0]?.unit}
          />
        </section>
      )}

      {relatedResources.length > 0 && (
        <section className="insight-drawer__property-group drawer-trends__related-section">
          <h4 className="insight-drawer__property-group-title">Related resources assessed</h4>
          <ul className="drawer-trends__related-items">
            {relatedResources.map((rel) => (
              <li key={rel.id}>
                <span className="drawer-trends__related-name">{rel.label}</span>
                <span className="drawer-trends__related-relation">{rel.relation}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
