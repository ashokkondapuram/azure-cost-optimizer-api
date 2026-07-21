import React, { useMemo } from 'react';
import { toDisplayText } from '../../utils/formatDisplay';
import { formatDateTime } from '../../utils/format';
import ResourceInventoryProperties from '../ResourceInventoryProperties';
import { formatPropertyValue } from '../../utils/format';
import { formatFactValue } from '../../utils/resourceMetricsUtils';

const ARM_PROPERTY_SKIP = new Set([
  'provisioningState',
]);

function ArmPropertiesTable({ properties = {} }) {
  const rows = useMemo(() => {
    if (!properties || typeof properties !== 'object') return [];
    return Object.entries(properties)
      .filter(([key]) => !ARM_PROPERTY_SKIP.has(key))
      .slice(0, 24)
      .map(([key, value]) => ({
        fact_key: key,
        label: key.replace(/([A-Z])/g, ' $1').replace(/^./, (c) => c.toUpperCase()),
        value,
        formatted: formatPropertyValue(value),
      }));
  }, [properties]);

  if (!rows.length) return null;
  return <ResourceInventoryProperties properties={rows} />;
}

function MetricsSummary({ metricsData }) {
  const rows = useMemo(() => {
    const list = [
      ...(metricsData?.derived || []),
      ...(metricsData?.metrics || []),
    ];
    return list.slice(0, 10).map((m) => ({
      label: m.label || m.name || m.id,
      value: m.formatted
        ?? formatFactValue(m.fact_key, m.value ?? m.stats?.average ?? m.stats?.[m.primary_stat], m.unit),
    })).filter((r) => r.label && r.value != null && r.value !== '—');
  }, [metricsData]);

  if (!rows.length) return null;

  return (
    <div className="wiz-metrics-summary">
      <div className="wiz-impact-banner__label">Key metrics</div>
      <div className="wiz-detail__meta-grid" style={{ marginTop: '0.35rem' }}>
        {rows.map((row) => (
          <div key={row.label} className="wiz-meta-item">
            <label>{row.label}</label>
            <span>{String(row.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ResourceProfileSection({
  resource,
  metricsData,
  compact = false,
}) {
  if (!resource) return null;

  const tags = resource.tags && typeof resource.tags === 'object' ? resource.tags : {};
  const tagEntries = Object.entries(tags).slice(0, compact ? 4 : 8);
  const inventoryProps = metricsData?.inventory_properties || [];
  const armProps = resource.properties || {};

  return (
    <section className={`wiz-resource-profile${compact ? ' wiz-resource-profile--compact' : ''}`}>
      <div className="wiz-detail__meta-grid">
        <div className="wiz-meta-item">
          <label>Location</label>
          <span>{toDisplayText(resource.location) || '—'}</span>
        </div>
        <div className="wiz-meta-item">
          <label>SKU</label>
          <span>{toDisplayText(resource.sku) || '—'}</span>
        </div>
        <div className="wiz-meta-item">
          <label>State</label>
          <span>{toDisplayText(resource.state || resource._state) || '—'}</span>
        </div>
        <div className="wiz-meta-item">
          <label>ARM type</label>
          <span style={{ fontSize: '0.78rem', wordBreak: 'break-all' }}>{toDisplayText(resource.type) || '—'}</span>
        </div>
        {resource.azureStatus && (
          <div className="wiz-meta-item">
            <label>Azure status</label>
            <span>{toDisplayText(resource.azureStatus)}</span>
          </div>
        )}
        {resource.syncedAt && (
          <div className="wiz-meta-item">
            <label>Last synced</label>
            <span>{formatDateTime(resource.syncedAt)}</span>
          </div>
        )}
        {resource.azureServiceName && (
          <div className="wiz-meta-item">
            <label>Service</label>
            <span>{resource.azureServiceName}</span>
          </div>
        )}
      </div>

      {tagEntries.length > 0 && (
        <div style={{ marginTop: '0.65rem' }}>
          <div className="wiz-impact-banner__label">Tags</div>
          <div className="wiz-pill-row" style={{ marginTop: '0.35rem' }}>
            {tagEntries.map(([key, value]) => (
              <span key={key} className="wiz-pill" title={`${key}: ${value}`}>
                {key}
                :
                {String(value)}
              </span>
            ))}
          </div>
        </div>
      )}

      <MetricsSummary metricsData={metricsData} />

      {inventoryProps.length > 0 && (
        <div style={{ marginTop: '0.65rem' }}>
          <ResourceInventoryProperties properties={inventoryProps} />
        </div>
      )}

      {!inventoryProps.length && Object.keys(armProps).length > 0 && (
        <div style={{ marginTop: '0.65rem' }}>
          <ArmPropertiesTable properties={armProps} />
        </div>
      )}
    </section>
  );
}
