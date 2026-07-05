import React from 'react';
import { X } from 'lucide-react';
import OptimizationActionChip from './OptimizationActionChip';
import ConfidenceScore from './ConfidenceScore';
import ActionCombinedEvidence from './ActionCombinedEvidence';
import { formatCurrency } from '../../utils/format';
import { workflowStatusLabel } from '../../utils/actionUtils';
import { resourceGroupLabelForAction } from '../../utils/optimizationGrouping';
import { tierLabel, tierTone } from '../../utils/actionAnalysisUtils';

function ActionDetailContent({
  action,
  currency,
  onClose,
  onApproveClick,
  isAdmin,
  compact = false,
}) {
  return (
    <>
      <header className="action-detail-drawer__header">
        <div>
          <h2 id="action-detail-title" className="action-detail-drawer__title">
            {action.resource_name}
          </h2>
          <p className="action-detail-drawer__subtitle">
            {action.resource_type} • {action.resource_group || resourceGroupLabelForAction(action)}
          </p>
        </div>
        <button
          type="button"
          className="btn-icon"
          onClick={onClose}
          aria-label="Close"
        >
          <X size={compact ? 18 : 20} />
        </button>
      </header>

      <div className="action-detail-drawer__body">
        <section className="drawer-section">
          <h3 className="drawer-section__title">Action summary</h3>
          <div className="drawer-summary-grid">
            <div className="drawer-summary-item">
              <span className="drawer-summary-label">Type</span>
              <div className="drawer-summary-value">
                <OptimizationActionChip actionType={action.action_type} />
              </div>
            </div>
            <div className="drawer-summary-item">
              <span className="drawer-summary-label">Confidence</span>
              <div className="drawer-summary-value">
                <ConfidenceScore confidence={action.confidence} compact />
              </div>
            </div>
            <div className="drawer-summary-item">
              <span className="drawer-summary-label">Status</span>
              <div className="drawer-summary-value">
                <span className="workflow-pill">
                  {workflowStatusLabel(action.workflow_status)}
                </span>
              </div>
            </div>
            {action.recommendation_tier && (
              <div className="drawer-summary-item">
                <span className="drawer-summary-label">Tier</span>
                <div className="drawer-summary-value">
                  <span className={`tier-pill tier-pill--${tierTone(action.recommendation_tier)}`}>
                    {tierLabel(action.recommendation_tier)}
                  </span>
                </div>
              </div>
            )}
            {action.overall_score != null && (
              <div className="drawer-summary-item">
                <span className="drawer-summary-label">Overall score</span>
                <div className="drawer-summary-value">{Math.round(action.overall_score)}</div>
              </div>
            )}
            {action.estimated_monthly_savings > 0 && (
              <div className="drawer-summary-item">
                <span className="drawer-summary-label">Est. savings/mo</span>
                <div className="drawer-summary-value text-highlight">
                  {formatCurrency(action.estimated_monthly_savings, { currency })}
                </div>
              </div>
            )}
          </div>
        </section>

        {action.action_reason && (
          <section className="drawer-section">
            <h3 className="drawer-section__title">Recommendation</h3>
            <p className="drawer-section-text">{action.action_reason}</p>
          </section>
        )}

        <ActionCombinedEvidence action={action} currency={currency} />
      </div>

      <footer className="action-detail-drawer__footer">
        <button
          type="button"
          className="btn btn--ghost"
          onClick={onClose}
        >
          Close
        </button>
        {isAdmin && (
          <button
            type="button"
            className="btn btn--primary"
            onClick={onApproveClick}
          >
            Approve/Update
          </button>
        )}
      </footer>
    </>
  );
}

export default function ActionDetailDrawer({
  action,
  currency = 'USD',
  onClose,
  onApproveClick,
  isAdmin = false,
  variant = 'overlay',
}) {
  if (!action) return null;

  if (variant === 'sidebar') {
    return (
      <aside
        className="action-detail-sidebar"
        role="complementary"
        aria-labelledby="action-detail-title"
      >
        <ActionDetailContent
          action={action}
          currency={currency}
          onClose={onClose}
          onApproveClick={onApproveClick}
          isAdmin={isAdmin}
          compact
        />
      </aside>
    );
  }

  return (
    <div className="action-detail-drawer-overlay" role="presentation" onClick={onClose}>
      <div
        className="action-detail-drawer"
        role="dialog"
        aria-labelledby="action-detail-title"
        onClick={(e) => e.stopPropagation()}
      >
        <ActionDetailContent
          action={action}
          currency={currency}
          onClose={onClose}
          onApproveClick={onApproveClick}
          isAdmin={isAdmin}
        />
      </div>
    </div>
  );
}
