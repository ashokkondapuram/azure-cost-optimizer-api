import React from 'react';
import {
  formatPropertyValue,
  isComplexPropertyValue,
  formatDateTime,
} from '../utils/format';
import { formatFactValue } from '../utils/resourceMetricsUtils';
import ArmResourceLink from './ArmResourceLink';
import { isArmResourceId } from '../utils/armResourceLinks';

const URL_RE = /^https?:\/\//i;

function PropertyValue({ value, formatted, factKey, unit }) {
  const armCandidate = typeof value === 'string'
    ? value
    : (typeof formatted === 'string' ? formatted : '');
  if (isArmResourceId(armCandidate)) {
    return <ArmResourceLink resourceId={armCandidate} className="property-value" />;
  }

  if (formatted != null && formatted !== '' && formatted !== '—') {
    return <span className="property-value">{formatted}</span>;
  }

  if (factKey) {
    const factFormatted = formatFactValue(factKey, value, unit);
    if (factFormatted !== '—') {
      return <span className="property-value">{factFormatted}</span>;
    }
  }

  if (typeof value === 'string' && URL_RE.test(value.trim())) {
    return (
      <a className="property-value property-value--link" href={value.trim()} target="_blank" rel="noopener noreferrer">
        {value.trim()}
      </a>
    );
  }

  if (isComplexPropertyValue(value)) {
    const summary = formatPropertyValue(value);
    return (
      <details className="expandable-value">
        <summary className="property-value property-value--summary">{summary}</summary>
        <pre className="value-details">{formatPropertyValue(value, { expand: true })}</pre>
      </details>
    );
  }

  const display = formatPropertyValue(value);
  if (value instanceof Date || (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value))) {
    return <span className="property-value">{formatDateTime(value)}</span>;
  }

  return <span className="property-value">{display}</span>;
}

export default function ResourceInventoryProperties({
  properties = [],
  hideTitle = false,
  compact = false,
}) {
  const rows = (properties || []).filter((row) => {
    const value = row?.value;
    const formatted = row?.formatted;
    if (formatted && formatted !== '—') return true;
    if (value == null || value === '') return false;
    return true;
  });

  if (!rows.length) {
    return <p className="insight-drawer__empty">No properties available for this resource yet.</p>;
  }

  return (
    <div className={`properties-section resource-inventory-properties${compact ? ' resource-inventory-properties--compact' : ''}`}>
      {!hideTitle && (
        <h4 className="properties-title resource-inventory-properties__title">Properties</h4>
      )}
      <div className="table-wrap resource-metrics-table-wrap">
        <table className="properties-table resource-metrics-table">
          <thead>
            <tr>
              <th scope="col" className="properties-col--name">Property</th>
              <th scope="col" className="properties-col--value">Value</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const label = row.label || row.fact_key || '—';
              return (
                <tr key={row.fact_key || row.label || i} className={i % 2 === 0 ? 'row--alt' : ''}>
                  <td className="property-name" title={label}>{label}</td>
                  <td className="property-value-cell">
                    <PropertyValue
                      value={row.value}
                      formatted={row.formatted}
                      factKey={row.fact_key}
                      unit={row.unit}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
