import React from 'react';
import { useNavigate } from 'react-router-dom';
import AssetIcon from '../AssetIcon';
import { formatCurrency } from '../../utils/format';
import {
  DEFAULT_AC_SORT,
  SOURCE_CHIP_LABELS,
  WORKFLOW_CHIP_LABELS,
  encodeResourceRouteId,
} from '../../utils/actionCentreV2Utils';

const COLUMNS = [
  { key: 'resource', label: 'Resource' },
  { key: 'recommendation', label: 'Recommendation' },
  { key: 'category', label: 'Category' },
  { key: 'cost', label: 'Monthly cost' },
  { key: 'savings', label: 'Savings', defaultDir: 'desc' },
  { key: 'severity', label: 'Severity' },
  { key: 'source', label: 'Source' },
  { key: 'status', label: 'Status' },
];

const SEVERITY_LABELS = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

function sortClass(col, sortKey) {
  const [activeCol, dir] = sortKey.split('-');
  if (activeCol !== col) return 'ac-sortable';
  return `ac-sortable active ${dir}`;
}

const EMPTY_MESSAGES = {
  filtered: {
    message: 'No findings match your filters.',
    showClear: true,
  },
  no_sync: {
    message: 'Sync resources and costs for this subscription to populate the action centre.',
    showClear: false,
  },
  no_analysis: {
    message: 'No analysis has run yet. Run analysis from Settings to generate findings.',
    showClear: false,
  },
  empty_queue: {
    message: 'No open findings in the queue. Your environment looks clear for now.',
    showClear: false,
  },
};

export default function ActionCentreFindingsTable({
  rows = [],
  sort = DEFAULT_AC_SORT,
  onSort,
  totalCount = 0,
  truncated = false,
  hasActiveFilters = false,
  emptyState = null,
  isLoadingMore = false,
  currency = 'CAD',
  onClearFilters,
}) {
  const navigate = useNavigate();
  const isEmpty = rows.length === 0;
  const extra = Math.max(0, totalCount - rows.length);

  const openRow = (row) => {
    if (!row?.resourceId) return;
    navigate(`/resource/${encodeResourceRouteId(row.resourceId)}`);
  };

  return (
    <div className={`panel table-panel ac-table-panel${isEmpty ? ' ac-table-panel--empty' : ''}`}>
      <div className="ac-table-head">
        <h2 className="section-title section-title--bar">Findings queue</h2>
        <span className="ac-table-head__count">{rows.length}</span>
      </div>
      {!isEmpty && (
        <div className="ac-table-scroll">
          <table className="ac-findings-table" id="ac-findings-table">
            <thead>
              <tr>
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    className={sortClass(col.key, sort)}
                    data-sort-col={col.key}
                    scope="col"
                    onClick={() => onSort(col.key)}
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody id="ac-findings-tbody">
              {rows.map((row) => (
                <tr
                  key={row.findingId || row.id}
                  data-finding-id={row.id}
                  tabIndex={0}
                  aria-label={`${row.resource} — ${row.recommendation}`}
                  onClick={() => openRow(row)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      openRow(row);
                    }
                  }}
                >
                  <td>
                    <div className="resource-cell">
                      <AssetIcon iconKey={row.iconKey} size={32} className="resource-icon" />
                      <div>
                        <strong>{row.resource}</strong>
                        <span className="resource-cell__meta">
                          {row.rg}
                          {' '}
                          ·
                          {' '}
                          {row.typeLabel}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td className="ac-table-rec">
                    <div className="ac-table-rec__text">{row.recommendation}</div>
                    {row.recommendationCount > 1 ? (
                      <span className="ac-rec-count-badge">
                        {row.recommendationCount}
                        {' '}
                        recommendations
                      </span>
                    ) : null}
                  </td>
                  <td className="ac-table-category">{row.categoryLabel}</td>
                  <td className="ac-table-cost">
                    {formatCurrency(row.cost, { currency, decimals: 2 })}
                  </td>
                  <td className="ac-table-savings">
                    {formatCurrency(row.savings, { currency, decimals: 0 })}
                  </td>
                  <td>
                    <span className={`sev sev-${row.severity}`}>
                      {SEVERITY_LABELS[row.severity] || row.severity}
                    </span>
                  </td>
                  <td>
                    <span className={`source-tag source-tag--${row.source}`}>
                      {SOURCE_CHIP_LABELS[row.source] || row.source}
                    </span>
                  </td>
                  <td>
                    <span className={`workflow-badge workflow-badge--${row.workflow}`}>
                      {WORKFLOW_CHIP_LABELS[row.workflow] || row.workflow}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!isEmpty && extra > 0 && (
        <p className="ac-queue-more">
          +
          {extra}
          {' '}
          more in full queue
        </p>
      )}
      {!isEmpty && truncated && extra === 0 && !hasActiveFilters && (
        <p className="ac-queue-more">More findings available — sync to refresh</p>
      )}
      {isEmpty && (
        <p className="ac-empty">
          {EMPTY_MESSAGES[emptyState]?.message || EMPTY_MESSAGES.filtered.message}
          {EMPTY_MESSAGES[emptyState]?.showClear !== false && hasActiveFilters && (
            <>
              {' '}
              <button type="button" className="link link--sm" onClick={onClearFilters}>
                Clear filters
              </button>
            </>
          )}
        </p>
      )}
      {isEmpty && isLoadingMore && (
        <p className="ac-empty text-muted text-sm">Loading resource details…</p>
      )}
    </div>
  );
}
