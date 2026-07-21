import React from 'react';

function DriverRow({ driver }) {
  const kindLabel = driver.kind === 'property'
    ? 'Property'
    : driver.kind === 'metric'
      ? 'Metric'
      : 'Cost signal';

  return (
    <tr>
      <td><span className="badge badge-info">{kindLabel}</span></td>
      <td>{driver.label || driver.fact_key}</td>
      <td><code>{driver.fact_key}</code></td>
      <td>{driver.source || driver.metric_name || '—'}</td>
      <td>{(driver.rules || []).join(', ') || '—'}</td>
    </tr>
  );
}

export default function CostDriverMappingPanel({ mapping, compact = false }) {
  const drivers = mapping?.cost_drivers || [];
  if (!drivers.length) return null;

  if (compact) {
    return (
      <div className="cost-driver-mapping cost-driver-mapping--compact">
        <ul className="cost-driver-mapping__list">
          {drivers.map((driver) => {
            const kindLabel = driver.kind === 'property'
              ? 'Property'
              : driver.kind === 'metric'
                ? 'Metric'
                : 'Cost signal';
            return (
              <li key={`${driver.kind}-${driver.fact_key}`} className="cost-driver-mapping__list-item">
                <span className="badge badge-info">{kindLabel}</span>
                <span className="cost-driver-mapping__list-label">{driver.label || driver.fact_key}</span>
                <code className="cost-driver-mapping__list-key">{driver.fact_key}</code>
              </li>
            );
          })}
        </ul>
      </div>
    );
  }

  return (
    <div className="cost-driver-mapping">
      <h4 className="cost-driver-mapping__title">Cost-driving signals</h4>
      <p className="cost-driver-mapping__hint text-muted">
        Inventory properties and metrics used to evaluate cost recommendations for{' '}
        {mapping?.display_name || mapping?.canonical_type || 'this resource type'}.
      </p>
      <div className="table-wrap">
        <table className="cost-driver-mapping__table">
          <thead>
            <tr>
              <th scope="col">Kind</th>
              <th scope="col">Label</th>
              <th scope="col">Fact key</th>
              <th scope="col">Source</th>
              <th scope="col">Rules</th>
            </tr>
          </thead>
          <tbody>
            {drivers.map((driver) => (
              <DriverRow key={`${driver.kind}-${driver.fact_key}`} driver={driver} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
