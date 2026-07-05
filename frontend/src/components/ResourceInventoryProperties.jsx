import React from 'react';
import {
  formatPropertyValue,
  isComplexPropertyValue,
  formatDateTime,
} from '../utils/format';
import ArmResourceLink from './ArmResourceLink';
import { isArmResourceId } from '../utils/armResourceLinks';

const URL_RE = /^https?:\/\//i;

function PropertyValue({ value, formatted }) {
  const armCandidate = typeof value === 'string'
    ? value
    : (typeof formatted === 'string' ? formatted : '');
  if (isArmResourceId(armCandidate)) {
    return <ArmResourceLink resourceId={armCandidate} className="property-value" />;
  }

  if (formatted != null && formatted !== '') {
    return <span className="property-value">{formatted}</span>;
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

export default function ResourceInventoryProperties({ properties = [] }) {
  if (!properties?.length) return null;

  return (
    <div className="properties-section resource-inventory-properties">
      <h4 className="properties-title resource-inventory-properties__title">Properties</h4>
      <div className="table-wrap resource-metrics-table-wrap">
        <table className="properties-table resource-metrics-table">
          <thead>
            <tr>
              <th scope="col" className="properties-col--name">Property</th>
              <th scope="col" className="properties-col--value">Value</th>
            </tr>
          </thead>
          <tbody>
            {properties.map((row, i) => {
              const label = row.label || row.fact_key || '—';
              return (
                <tr key={row.fact_key || row.label || i} className={i % 2 === 0 ? 'row--alt' : ''}>
                  <td className="property-name" title={label}>{label}</td>
                  <td className="property-value-cell">
                    <PropertyValue value={row.value} formatted={row.formatted} />
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
