import React, { memo } from 'react';
import ActionResourceCell from './ActionResourceCell';
import OptimizationActionChip from './OptimizationActionChip';
import { formatCurrency } from '../../utils/format';
import { workflowStatusLabel } from '../../utils/actionUtils';

function ActionTableRow({
  action,
  currency,
  isAdmin,
  selected,
  isReviewing,
  onToggleSelect,
  onReview,
  variant = 'table',
}) {
  const savings = action.estimated_monthly_savings > 0
    ? formatCurrency(action.estimated_monthly_savings, { currency })
    : '—';
  const status = action.workflow_status || 'proposed';
  const rowClass = `data-table__row--clickable${isReviewing ? ' data-table__row--selected' : ''}`;

  const handleReview = (event) => {
    event?.stopPropagation?.();
    onReview(action);
  };

  if (variant === 'virtual') {
    return (
      <div
        className={`virtual-action-row ${rowClass}`}
        onClick={() => onReview(action)}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            onReview(action);
          }
        }}
      >
        {isAdmin && (
          <div className="virtual-action-row__cell" onClick={(event) => event.stopPropagation()}>
            <input
              type="checkbox"
              aria-label={`Select ${action.resource_name}`}
              checked={selected}
              onChange={() => onToggleSelect(action.id)}
            />
          </div>
        )}
        <div className="virtual-action-row__cell virtual-action-row__cell--resource">
          <ActionResourceCell action={action} compact />
        </div>
        <div className="virtual-action-row__cell virtual-action-row__cell--action">
          <OptimizationActionChip actionType={action.action_type} />
        </div>
        <div className="virtual-action-row__cell virtual-action-row__cell--savings">{savings}</div>
        <div className="virtual-action-row__cell virtual-action-row__cell--status">
          <span className={`workflow-pill workflow-pill--${status}`}>{workflowStatusLabel(status)}</span>
        </div>
        <div className="virtual-action-row__cell virtual-action-row__cell--review" onClick={(event) => event.stopPropagation()}>
          <button type="button" className="btn btn-ghost btn-sm" onClick={handleReview}>
            Review
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      {isAdmin && (
        <td onClick={(event) => event.stopPropagation()}>
          <input
            type="checkbox"
            aria-label={`Select ${action.resource_name}`}
            checked={selected}
            onChange={() => onToggleSelect(action.id)}
          />
        </td>
      )}
      <td className="action-table__resource">
        <ActionResourceCell action={action} compact />
      </td>
      <td className="action-table__action">
        <OptimizationActionChip actionType={action.action_type} />
      </td>
      <td className="action-table__savings">{savings}</td>
      <td className="action-table__status">
        <span className={`workflow-pill workflow-pill--${status}`}>{workflowStatusLabel(status)}</span>
      </td>
      <td className="action-table__review" onClick={(event) => event.stopPropagation()}>
        <button type="button" className="btn btn-ghost btn-sm" onClick={handleReview}>
          Review
        </button>
      </td>
    </>
  );
}

export default memo(ActionTableRow);
