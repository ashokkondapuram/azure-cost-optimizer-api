import React from 'react';
import {
  formatMetricStatValue,
  normalizeMetricRow,
  optimizationMetricStatusLabel,
  statColumnsForRows,
} from '../utils/resourceMetricsUtils';

function MetricsTable({ rows, metricNameKey = 'metric_name', labelKey = 'label' }) {
  const normalizedRows = (rows || []).map(normalizeMetricRow).filter(Boolean);
  if (!normalizedRows.length) return null;

  const columns = statColumnsForRows(normalizedRows);

  return (
    <div className="table-wrap resource-metrics-table-wrap">
      <table className="resource-metrics-table">
        <thead>
          <tr>
            <th scope="col">Metric</th>
            {columns.map((col) => (
              <th key={col.key} scope="col">{col.label}</th>
            ))}
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {normalizedRows.map((row) => {
            const stats = row.stats || {};
            const metricKey = row[metricNameKey] || row.fact_key;
            return (
              <tr key={`${metricKey}-${row.fact_key || row.label}`}>
                <th scope="row" title={metricKey}>
                  {row[labelKey] || metricKey}
                  {row.isDerived && (
                    <span className="resource-metrics-derived" title="Computed metric"> · computed</span>
                  )}
                </th>
                {columns.map((col) => (
                  <td key={col.key} className={stats[col.key] == null ? 'resource-azure-metrics__empty' : ''}>
                    {formatMetricStatValue(row.fact_key, stats[col.key], row.unit)}
                  </td>
                ))}
                <td>
                  {row.status ? (
                    <span className={`resource-metrics-status resource-metrics-status--${row.status}`}>
                      {optimizationMetricStatusLabel(row.status)}
                    </span>
                  ) : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function ResourceMetricsDetailTable({
  metricsDetail = [],
  metrics = [],
  derived = [],
  instances = [],
}) {
  const aggregateRows = metrics?.length
    ? metrics.map((row) => normalizeMetricRow({
      ...row,
      stats: row.stats || {},
      isDerived: false,
    }))
    : (metricsDetail || []).map((row) => normalizeMetricRow({ ...row, isDerived: false }));

  const derivedRows = (derived || []).map((row) => normalizeMetricRow({
    fact_key: row.fact_key,
    label: row.label,
    unit: row.unit,
    stats: {
      average: row.value,
      maximum: row.value,
      minimum: row.value,
    },
    display_stats: ['average', 'minimum', 'maximum'],
    status: row.status,
    isDerived: true,
  }));

  const allAggregate = [...aggregateRows, ...derivedRows];

  if (!allAggregate.length && !instances.length) return null;

  return (
    <div className="resource-metrics-detail">
      {allAggregate.length > 0 && (
        <MetricsTable rows={allAggregate} />
      )}

      {instances.length > 0 && (
        <div className="resource-metrics-instances">
          <h4 className="resource-metrics-instances__title">
            {instances[0]?.source === 'k8s_agent' ? 'Nodes' : 'Instances'}
          </h4>
          {instances.map((instance) => (
            <details key={instance.resource_id || instance.instance_id} className="resource-metrics-instance">
              <summary>
                {instance.name || instance.instance_id}
                {instance.instance_id && instance.name !== instance.instance_id && (
                  <span className="resource-metrics-instance__id"> · {instance.instance_id}</span>
                )}
              </summary>
              <MetricsTable rows={instance.metrics_detail || []} />
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
