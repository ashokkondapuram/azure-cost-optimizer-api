import React from 'react';
import { X } from 'lucide-react';
import OptimizationActionChip from './OptimizationActionChip';
import ConfidenceScore from './ConfidenceScore';
import ActionCombinedEvidence from './ActionCombinedEvidence';
import ActionDetailResourcePanel from './ActionDetailResourcePanel';
import ActionEvidenceSignals from './ActionEvidenceSignals';
import { formatCurrency } from '../../utils/format';
import {
  workflowStatusLabel,
  actionResourceDisplayName,
  actionResourceMetaLine,
} from '../../utils/actionUtils';
import { tierLabel, tierTone } from '../../utils/actionAnalysisUtils';

function ActionDetailKpis({ action, currency }) {
  const savings = Number(action.estimated_monthly_savings) || 0;

  return (
    <div className="action-detail-kpis" role="list" aria-label="Action summary">
      <div className="action-detail-kpis__item" role="listitem">
        <span className="action-detail-kpis__label">Action</span>
        <OptimizationActionChip actionType={action.action_type} />
      </div>
      <div className="action-detail-kpis__item" role="listitem">
        <span className="action-detail-kpis__label">Confidence</span>
        <ConfidenceScore confidence={action.confidence} compact />
      </div>
      <div className="action-detail-kpis__item" role="listitem">
        <span className="action-detail-kpis__label">Status</span>
        <span className={`workflow-pill workflow-pill--${action.workflow_status || 'proposed'}`}>
          {workflowStatusLabel(action.workflow_status)}
        </span>
      </div>
      {savings > 0 && (
        <div className="action-detail-kpis__item action-detail-kpis__item--savings" role="listitem">
          <span className="action-detail-kpis__label">Est. savings</span>
          <strong className="action-detail-kpis__savings">
            {formatCurrency(savings, { currency })}
            <span className="action-detail-kpis__savings-unit">/mo</span>
          </strong>
        </div>
      )}
      {action.performance_risk && (
        <div className="action-detail-kpis__item" role="listitem">
          <span className="action-detail-kpis__label">Risk</span>
          <span className="action-detail-kpis__value">{action.performance_risk}</span>
        </div>
      )}
      {action.recommendation_tier && (
        <div className="action-detail-kpis__item" role="listitem">
          <span className="action-detail-kpis__label">Tier</span>
          <span className={`tier-pill tier-pill--${tierTone(action.recommendation_tier)}`}>
            {tierLabel(action.recommendation_tier)}
          </span>
        </div>
      )}
      {action.overall_score != null && (
        <div className="action-detail-kpis__item" role="listitem">
          <span className="action-detail-kpis__label">Score</span>
          <span className="action-detail-kpis__value">{Math.round(action.overall_score)}</span>
        </div>
      )}
    </div>
  );
}

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
        <div className="action-detail-drawer__header-main">
          <p className="action-detail-drawer__eyebrow">Optimization action</p>
          <h2 id="action-detail-title" className="action-detail-drawer__title">
            {actionResourceDisplayName(action)}
          </h2>
          <p className="action-detail-drawer__subtitle">
            {actionResourceMetaLine(action)}
          </p>
        </div>
        <button
          type="button"
          className="btn-icon action-detail-drawer__close"
          onClick={onClose}
          aria-label="Close"
        >
          <X size={compact ? 18 : 20} />
        </button>
      </header>

      <div className="action-detail-drawer__body">
        <ActionDetailResourcePanel action={action} />

        <ActionDetailKpis action={action} currency={currency} />

        {action.evidence_summary && (
          <section className="action-detail-drawer__section action-detail-drawer__section--signals">
            <h3 className="action-detail-drawer__section-title">Signals</h3>
            <ActionEvidenceSignals summary={action.evidence_summary} />
          </section>
        )}

        {action.action_reason && (
          <section className="action-detail-drawer__section">
            <h3 className="action-detail-drawer__section-title">Why this action</h3>
            <p className="action-detail-drawer__reason">{action.action_reason}</p>
          </section>
        )}

        <ActionCombinedEvidence action={action} currency={currency} showSignals={false} compact />
      </div>

      <footer className="action-detail-drawer__footer">
        <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
          Close
        </button>
        {isAdmin && (
          <button type="button" className="btn btn-primary btn-sm" onClick={onApproveClick}>
            Review action
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
