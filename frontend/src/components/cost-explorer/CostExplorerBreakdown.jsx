import React, { useMemo, useState } from 'react';
import { breakdownInsight, formatIsoCurrency } from '../../utils/costExplorerV2Utils';

const TABS = [
  { id: 'service', label: 'By service' },
  { id: 'rg', label: 'By resource group' },
  { id: 'region', label: 'By region' },
  { id: 'tag', label: 'By tag' },
];

function BreakdownPanel({ tab, rows, total, currency, active }) {
  const insight = useMemo(
    () => breakdownInsight(tab, rows, total, currency),
    [tab, rows, total, currency],
  );

  return (
    <div
      className={`ce-breakdown-panel${active ? ' active' : ''}`}
      id={`ce-tab-${tab}`}
      role="tabpanel"
      hidden={!active}
    >
      <p className="breakdown-insight">{insight}</p>
      {rows.length === 0 ? (
        <p className="panel-empty">
          {tab === 'region'
            ? 'Region breakdown is not available from synced cost data yet.'
            : tab === 'tag'
              ? 'Tag-based spend breakdown is not available from synced cost data yet.'
              : 'No breakdown data for this period.'}
        </p>
      ) : (
        <div className="category-chart category-chart--compact ce-breakdown-chart">
          {rows.slice(0, 8).map((row) => (
            <div
              key={row.key}
              className="category-row ce-bar-row"
              data-ce-dimension={tab}
              data-ce-key={row.key}
              tabIndex={0}
            >
              <span className="category-label">
                <span className="cat-dot" style={{ '--cat-color': row.color }} />
                {row.name}
              </span>
              <div className="category-track">
                <div
                  className="category-fill"
                  style={{ width: `${row.widthPct}%`, '--cat-color': row.color }}
                />
              </div>
              <span className="category-count" data-currency={currency}>
                {formatIsoCurrency(row.cost, currency, { decimals: 0 }).replace(`${currency} `, '')}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function CostExplorerBreakdown({
  serviceRows,
  rgRows,
  regionRows,
  tagRows,
  total,
  currency,
}) {
  const [activeTab, setActiveTab] = useState('service');

  const rowsByTab = useMemo(() => ({
    service: serviceRows,
    rg: rgRows,
    region: regionRows,
    tag: tagRows,
  }), [serviceRows, rgRows, regionRows, tagRows]);

  return (
    <div className="panel ce-breakdown-panel-wrap" id="ce-breakdown-panel">
      <div className="panel-head panel-head--inset panel-head--split">
        <h2 className="section-title section-title--bar">Spend breakdown</h2>
        <span className="panel-sub" id="ce-breakdown-total">{formatIsoCurrency(total, currency, { decimals: 0 })} total</span>
      </div>
      <div className="breakdown-tabs ce-breakdown-tabs" role="tablist" aria-label="Breakdown dimension">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            className={`breakdown-tab ce-breakdown-tab${activeTab === tab.id ? ' active' : ''}`}
            role="tab"
            aria-selected={activeTab === tab.id}
            data-ce-tab={tab.id}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {TABS.map((tab) => (
        <BreakdownPanel
          key={tab.id}
          tab={tab.id}
          rows={rowsByTab[tab.id] || []}
          total={total}
          currency={currency}
          active={activeTab === tab.id}
        />
      ))}
    </div>
  );
}
