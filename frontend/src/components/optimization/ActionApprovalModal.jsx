import React, { useEffect, useMemo, useState } from 'react';
import {
  CheckCircle2,
  CircleCheck,
  PauseCircle,
  RotateCcw,
  User,
  X,
  XCircle,
} from 'lucide-react';
import OptimizationActionChip from './OptimizationActionChip';
import ConfidenceScore from './ConfidenceScore';
import { formatCurrency, formatDateTime } from '../../utils/format';
import { workflowStatusLabel } from '../../utils/actionUtils';
import { resourceGroupLabelForAction } from '../../utils/optimizationGrouping';

const WORKFLOW_OPTIONS = [
  {
    value: 'approved',
    label: 'Approve',
    description: 'Ready to implement',
    icon: CheckCircle2,
    tone: 'approved',
    adminOnly: true,
    cta: 'Approve action',
  },
  {
    value: 'executed',
    label: 'Executed',
    description: 'Change applied',
    icon: CircleCheck,
    tone: 'executed',
    adminOnly: true,
    cta: 'Mark executed',
  },
  {
    value: 'deferred',
    label: 'Defer',
    description: 'Review later',
    icon: PauseCircle,
    tone: 'deferred',
    cta: 'Defer action',
    noteRequired: true,
  },
  {
    value: 'rejected',
    label: 'Reject',
    description: 'Do not proceed',
    icon: XCircle,
    tone: 'rejected',
    adminOnly: true,
    cta: 'Reject action',
    noteRequired: true,
  },
  {
    value: 'proposed',
    label: 'Reopen',
    description: 'Back to proposed',
    icon: RotateCcw,
    tone: 'proposed',
    cta: 'Reopen action',
  },
];

function historyEntryLabel(entry) {
  const event = entry?.event || 'status_change';
  if (event === 'owner_change') {
    if (entry.owner_to) {
      return `Assigned to ${entry.owner_to}`;
    }
    return 'Owner cleared';
  }
  if (event === 'note') {
    return 'Note added';
  }
  if (entry.from_status === entry.to_status) {
    return workflowStatusLabel(entry.to_status);
  }
  return `${workflowStatusLabel(entry.from_status)} → ${workflowStatusLabel(entry.to_status)}`;
}

function WorkflowHistory({ history = [] }) {
  if (!history.length) {
    return (
      <p className="action-approval-history__empty text-muted text-sm">
        No workflow activity yet.
      </p>
    );
  }

  const items = [...history].reverse().slice(0, 8);

  return (
    <ol className="action-approval-history">
      {items.map((entry, index) => (
        <li key={`${entry.at}-${index}`} className="action-approval-history__item">
          <span className={`action-approval-history__dot action-approval-history__dot--${entry.to_status || 'proposed'}`} aria-hidden />
          <div className="action-approval-history__content">
            <div className="action-approval-history__head">
              <strong>{historyEntryLabel(entry)}</strong>
              {entry.at && (
                <time className="action-approval-history__time" dateTime={entry.at}>
                  {formatDateTime(entry.at)}
                </time>
              )}
            </div>
            {entry.user_name && (
              <span className="action-approval-history__user">by {entry.user_name}</span>
            )}
            {entry.note && (
              <p className="action-approval-history__note">{entry.note}</p>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

export default function ActionApprovalModal({
  action,
  currency = 'USD',
  isAdmin,
  onClose,
  onSubmit,
  isPending = false,
}) {
  const currentStatus = action?.workflow_status || 'proposed';
  const [workflowStatus, setWorkflowStatus] = useState(currentStatus);
  const [owner, setOwner] = useState(action?.owner || '');
  const [note, setNote] = useState('');

  useEffect(() => {
    if (!action) return;
    setWorkflowStatus(action.workflow_status || 'proposed');
    setOwner(action.owner || '');
    setNote('');
  }, [action?.id, action?.workflow_status, action?.owner]);

  const selectedOption = useMemo(
    () => WORKFLOW_OPTIONS.find((option) => option.value === workflowStatus),
    [workflowStatus],
  );

  const visibleOptions = useMemo(
    () => WORKFLOW_OPTIONS.filter((option) => !option.adminOnly || isAdmin),
    [isAdmin],
  );

  if (!action) return null;

  const savings = action.estimated_monthly_savings;
  const ownerChanged = owner.trim() !== (action.owner || '');
  const statusChanged = workflowStatus !== currentStatus;
  const hasChanges = statusChanged || ownerChanged || note.trim().length > 0;
  const noteRequired = selectedOption?.noteRequired && statusChanged;
  const canSubmit = isAdmin
    && hasChanges
    && (!noteRequired || note.trim().length > 0)
    && !isPending;

  const handleSubmit = () => {
    const body = {};
    if (statusChanged) {
      body.workflow_status = workflowStatus;
    }
    if (ownerChanged) {
      if (owner.trim()) {
        body.owner = owner.trim();
      } else if (action.owner) {
        body.clear_owner = true;
      }
    }
    if (note.trim()) {
      body.note = note.trim();
    }
    if (!Object.keys(body).length) return;
    onSubmit(body);
  };

  return (
    <div className="modal-overlay action-approval-overlay" role="presentation" onClick={onClose}>
      <div
        className="modal-card action-approval-modal"
        role="dialog"
        aria-labelledby="action-approval-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="action-approval-modal__hero">
          <div className="action-approval-modal__hero-glow" aria-hidden />
          <div className="action-approval-modal__hero-content">
            <div className="action-approval-modal__hero-main">
              <p className="action-approval-modal__eyebrow">Workflow review</p>
              <h2 id="action-approval-title" className="action-approval-modal__title">
                {action.resource_name}
              </h2>
              <p className="action-approval-modal__subtitle">
                {action.resource_type} · {action.resource_group || resourceGroupLabelForAction(action)}
              </p>
              <div className="action-approval-modal__chips">
                <OptimizationActionChip actionType={action.action_type} />
                <ConfidenceScore confidence={action.confidence} compact />
                <span className={`workflow-pill workflow-pill--${currentStatus}`}>
                  {workflowStatusLabel(currentStatus)}
                </span>
              </div>
            </div>
            {savings > 0 && (
              <div className="action-approval-modal__savings-card">
                <span className="action-approval-modal__savings-label">Est. savings</span>
                <strong className="action-approval-modal__savings-value">
                  {formatCurrency(savings, { currency })}
                </strong>
                <span className="action-approval-modal__savings-sub">per month</span>
              </div>
            )}
          </div>
          <button type="button" className="btn-icon action-approval-modal__close" onClick={onClose} aria-label="Close">
            <X size={20} />
          </button>
        </header>

        <div className="action-approval-modal__body">
          {action.action_reason && (
            <section className="action-approval-panel action-approval-panel--reason">
              <h3 className="action-approval-panel__title">Recommendation</h3>
              <p className="action-approval-panel__text">{action.action_reason}</p>
            </section>
          )}

          {isAdmin && (
            <section className="action-approval-panel">
              <div className="action-approval-panel__head">
                <h3 className="action-approval-panel__title">Update status</h3>
                <span className="action-approval-panel__hint">Choose the next workflow step</span>
              </div>
              <div className="action-approval-status-grid" role="radiogroup" aria-label="Workflow status">
                {visibleOptions.map((option) => {
                  const Icon = option.icon;
                  const isSelected = workflowStatus === option.value;
                  const isCurrent = currentStatus === option.value;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      role="radio"
                      aria-checked={isSelected}
                      className={`action-approval-status-card action-approval-status-card--${option.tone}${isSelected ? ' action-approval-status-card--selected' : ''}${isCurrent ? ' action-approval-status-card--current' : ''}`}
                      onClick={() => setWorkflowStatus(option.value)}
                    >
                      <span className="action-approval-status-card__icon" aria-hidden>
                        <Icon size={18} />
                      </span>
                      <span className="action-approval-status-card__label">{option.label}</span>
                      <span className="action-approval-status-card__desc">{option.description}</span>
                      {isCurrent && (
                        <span className="action-approval-status-card__badge">Current</span>
                      )}
                    </button>
                  );
                })}
              </div>
            </section>
          )}

          {isAdmin && (
            <section className="action-approval-panel">
              <h3 className="action-approval-panel__title">Owner</h3>
              <label className="action-approval-owner-field">
                <User size={16} aria-hidden className="action-approval-owner-field__icon" />
                <input
                  type="text"
                  className="form-input action-approval-owner-field__input"
                  value={owner}
                  onChange={(e) => setOwner(e.target.value)}
                  placeholder="Team or email (optional)"
                  aria-label="Action owner"
                />
              </label>
            </section>
          )}

          <section className="action-approval-panel">
            <h3 className="action-approval-panel__title">
              {isAdmin ? 'Add note' : 'Activity'}
            </h3>
            {isAdmin ? (
              <>
                <textarea
                  className="form-textarea action-approval-note"
                  rows={3}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder={
                    noteRequired
                      ? 'Add a reason for this decision (required)…'
                      : 'Add context for the audit trail (optional)…'
                  }
                  aria-invalid={noteRequired && !note.trim()}
                />
                {noteRequired && !note.trim() && (
                  <p className="action-approval-note__hint">A note is required when rejecting or deferring.</p>
                )}
              </>
            ) : null}
            <div className="action-approval-history-wrap">
              <h4 className="action-approval-history__title">Recent activity</h4>
              <WorkflowHistory history={action.workflow_history} />
            </div>
          </section>
        </div>

        <footer className="modal-card__footer action-approval-modal__footer">
          <button type="button" className="btn btn--ghost" onClick={onClose} disabled={isPending}>
            Cancel
          </button>
          {isAdmin && (
            <button
              type="button"
              className={`btn btn--primary action-approval-modal__submit action-approval-modal__submit--${selectedOption?.tone || 'approved'}`}
              disabled={!canSubmit}
              onClick={handleSubmit}
            >
              {isPending ? 'Saving…' : (selectedOption?.cta || 'Save changes')}
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
