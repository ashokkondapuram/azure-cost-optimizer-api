import React from 'react';

const STATUS_TABS = [
  { id: 'open', label: 'Open' },
  { id: 'acknowledged', label: 'Acknowledged' },
  { id: 'implemented', label: 'Implemented' },
  { id: 'ignored', label: 'Dismissed' },
  { id: '', label: 'All' },
];

function countFor(map, key) {
  if (!map) return 0;
  return Number(map[key] ?? 0);
}

export default function RecommendationFilterTabs({
  summary,
  statusCounts,
  statusFilter,
  onStatusChange,
}) {
  const byStatus = statusCounts || summary?.by_status || {};
  const total = Number(summary?.total_findings ?? 0);

  return (
    <div className="rec-status-tabs" role="group" aria-label="Filter by status">
      {STATUS_TABS.map((tab) => {
        const count = tab.id ? countFor(byStatus, tab.id) : total;
        const active = statusFilter === tab.id;
        return (
          <button
            key={tab.id || '__all__'}
            type="button"
            aria-pressed={active}
            className={`rec-status-tab${active ? ' active' : ''}`}
            onClick={() => onStatusChange(tab.id)}
          >
            <span>{tab.label}</span>
            <span className="rec-status-tab__count">{count.toLocaleString()}</span>
          </button>
        );
      })}
    </div>
  );
}

export function buildRecommendationFilterSelects({
  summary,
  sevFilter,
  onSevChange,
  catFilter,
  onCatChange,
  typeFilter,
  onTypeChange,
}) {
  const bySeverity = summary?.by_severity || {};
  const byCategory = summary?.by_category || {};

  const severityOptions = [
    { value: '', label: 'All severities' },
    ...['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']
      .filter((key) => countFor(bySeverity, key) > 0)
      .map((key) => ({
        value: key,
        label: `${key.charAt(0) + key.slice(1).toLowerCase()} (${countFor(bySeverity, key)})`,
      })),
  ];

  const typeOptions = [
    { value: '', label: 'All types' },
    {
      value: 'cost',
      label: `Cost optimization (${Number(summary?.cost_optimization_findings ?? summary?.with_savings_findings ?? 0)})`,
    },
    {
      value: 'governance',
      label: `Governance (${Number(summary?.governance_findings ?? 0)})`,
    },
  ];

  const categoryOrder = ['COMPUTE', 'KUBERNETES', 'STORAGE', 'NETWORK', 'DATABASE', 'SECURITY', 'COST'];
  const categoryKeys = [
    ...categoryOrder.filter((key) => countFor(byCategory, key) > 0),
    ...Object.keys(byCategory).filter((key) => !categoryOrder.includes(key)).sort(),
  ];

  const categoryOptions = [
    { value: '', label: 'All categories' },
    ...categoryKeys.map((key) => ({
      value: key,
      label: `${key.charAt(0) + key.slice(1).toLowerCase()} (${countFor(byCategory, key)})`,
    })),
  ];

  return [
    {
      id: 'severity',
      label: 'Severity',
      value: sevFilter,
      onChange: onSevChange,
      options: severityOptions,
    },
    {
      id: 'type',
      label: 'Type',
      value: typeFilter,
      onChange: onTypeChange,
      options: typeOptions,
    },
    ...(categoryOptions.length > 1 ? [{
      id: 'category',
      label: 'Category',
      value: catFilter,
      onChange: onCatChange,
      options: categoryOptions,
    }] : []),
  ];
}
