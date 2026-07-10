import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  CheckCircle2,
  ChevronDown,
  CircleCheck,
  PauseCircle,
  RotateCcw,
  User,
  X,
  XCircle,
} from 'lucide-react';
import ModalPortal from '../ModalPortal';
import OptimizationActionChip from './OptimizationActionChip';
import ConfidenceScore from './ConfidenceScore';
import ActionDetailResourcePanel from './ActionDetailResourcePanel';
import ActionEvidenceSignals from './ActionEvidenceSignals';
import { formatCurrency, formatDateTime } from '../../utils/format';
import { workflowStatusLabel, actionResourceDisplayName, actionResourceMetaLine } from '../../utils/actionUtils';

const WORKFLOW_OPTIONS = [
  {
    value: 'approved',
    label: 'Approve',
    description: 'Ready to implement',
    icon: CheckCircle2,
    tone: 'approved',
    adminOnly: true,
    cta: 'Approve',
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
    cta: 'Defer',
    noteRequired: true,
  },
  {
    value: 'rejected',
    label: 'Reject',
    description: 'Do not proceed',
    icon: XCircle,
    tone: 'rejected',
    adminOnly: true,
    cta: 'Reject',
    noteRequired: true,
  },
  {
    value: 'proposed',
    label: 'Reopen',
    description: 'Back to proposed',
    icon: RotateCcw,
    tone: 'proposed',
    cta: 'Reopen',
  },
];

function ModalSection({ title, children, className = '' }) {
  return (
    <section className={`action-approval-section${className ? ` ${className}` : ''}`}>
      {title && <h3 className="action-approval-section__title">{title}</h3>}
      <div className="action-approval-section__content">{children}</div>
    </section>
  );
}

function CollapsibleSection({
  title,
  defaultOpen = false,
  className = '',
  children,
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className={`action-approval-section action-approval-section--collapsible${open ? ' is-open' : ''}${className ? ` ${className}` : ''}`}>
      <button
        type="button"
        className="action-approval-section__toggle"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <h3 className="action-approval-section__title">{title}</h3>
        <ChevronDown size={16} className="action-approval-section__chevron" aria-hidden />
      </button>
      {open && <div className="action-approval-section__content">{children}</div>}
    </section>
  );
}

function historyEntryLabel(entry) {
  const event = entry?.event || 'status_change';
  if (event === 'owner_change') {
    if (entry.owner_to) return `Assigned to ${entry.owner_to}`;
    return 'Owner cleared';
  }
  if (event === 'note') return 'Note added';
  if (entry.from_status === entry.to_status) return workflowStatusLabel(entry.to_status);
  return `${workflowStatusLabel(entry.from_status)} → ${workflowStatusLabel(entry.to_status)}`;
}

function WorkflowHistory({ history = [] }) {
  if (!history.length) {
    return <p className="action-approval-history__empty text-muted text-sm">No workflow activity yet.</p>;
  }

  const items = [...history].reverse().slice(0, 5);

  return (
    <ol className="action-approval-history">
      {items.map((entry, index) => (
        <li key={`${entry.at}-${index}`} className="action-approval-history__item">
          <span
            className={`action-approval-history__dot action-approval-history__dot--${entry.to_status || 'proposed'}`}
            aria-hidden
          />
          <div className="action-approval-history__content">
            <div className="action-approval-history__head">
              <strong>{historyEntryLabel(entry)}</strong>
              {entry.at && (
                <time className="action-approval-history__time" dateTime={entry.at}>
                  {formatDateTime(entry.at)}
                </time>
              )}
            </div>
            {entry.note && <p className="action-approval-history__note">{entry.note}</p>}
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
  const dialogRef = useRef(null);

  useEffect(() => {
    if (!action) return;
    setWorkflowStatus(action.workflow_status || 'proposed');
    setOwner(action.owner || '');
    setNote('');
  }, [action?.id, action?.workflow_status, action?.owner]);

  useEffect(() => {
    if (!action) return undefined;
    const onKeyDown = (event) => {
      if (event.key === 'Escape' && !isPending) onClose();
    };
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', onKeyDown);
    dialogRef.current?.focus();
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [action, isPending, onClose]);

  const selectedOption = useMemo(
    () => WORKFLOW_OPTIONS.find((option) => option.value === workflowStatus),
    [workflowStatus],
  );

  const visibleOptions = useMemo(
    () => WORKFLOW_OPTIONS.filter((option) => !option.adminOnly || isAdmin),
    [isAdmin],
  );

  if (!action) return null;

  const savings = Number(action.estimated_monthly_savings) || 0;
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
    if (statusChanged) body.workflow_status = workflowStatus;
    if (ownerChanged) {
      if (owner.trim()) body.owner = owner.trim();
      else if (action.owner) body.clear_owner = true;
    }
    if (note.trim()) body.note = note.trim();
    if (!Object.keys(body).length) return;
    onSubmit(body);
  };

  return (
    <ModalPortal>
      <div className="modal-overlay action-approval-overlay" role="presentation" onClick={onClose}>
        <div
          ref={dialogRef}
          className="modal-card action-approval-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="action-approval-title"
          tabIndex={-1}
          onClick={(e) => e.stopPropagation()}
        >
          <header className="action-approval-modal__header">
            <div className="action-approval-modal__header-text">
              <p className="action-approval-modal__eyebrow">Review action</p>
              <h2 id="action-approval-title" className="action-approval-modal__title">
                {actionResourceDisplayName(action)}
              </h2>
              <p className="action-approval-modal__subtitle">{actionResourceMetaLine(action)}</p>
            </div>
            <button
              type="button"
              className="btn-icon action-approval-modal__close"
              onClick={onClose}
              aria-label="Close"
            >
              <X size={18} />
            </button>
          </header>

          <div className="action-approval-summary" aria-label="Action summary">
            <div className="action-approval-summary__item">
              <span className="action-approval-summary__label">Action</span>
              <div className="action-approval-summary__value">
                <OptimizationActionChip actionType={action.action_type} />
              </div>
            </div>
            <div className="action-approval-summary__item">
              <span className="action-approval-summary__label">Status</span>
              <div className="action-approval-summary__value">
                <span className={`workflow-pill workflow-pill--${currentStatus}`}>
                  {workflowStatusLabel(currentStatus)}
                </span>
              </div>
            </div>
            <div className="action-approval-summary__item">
              <span className="action-approval-summary__label">Confidence</span>
              <div className="action-approval-summary__value">
                <ConfidenceScore confidence={action.confidence} compact />
              </div>
            </div>
            <div className="action-approval-summary__item action-approval-summary__item--savings">
              <span className="action-approval-summary__label">Est. savings</span>
              <div className="action-approval-summary__value action-approval-summary__value--savings">
                {savings > 0 ? (
                  <>
                    <strong>{formatCurrency(savings, { currency })}</strong>
                    <span className="action-approval-summary__unit">/mo</span>
                  </>
                ) : (
                  <span className="text-muted">—</span>
                )}
              </div>
            </div>
          </div>

          <div className="action-approval-modal__body">
            {action.evidence_summary && (
              <div className="action-approval-signals">
                <ActionEvidenceSignals summary={action.evidence_summary} compact />
              </div>
            )}

            <ModalSection title="Resource">
              <ActionDetailResourcePanel action={action} layout="modal" />
            </ModalSection>

            {action.action_reason && (
              <ModalSection title="Why this action" className="action-approval-section--reason">
                <p className="action-approval-section__text">{action.action_reason}</p>
              </ModalSection>
            )}

            {isAdmin && (
              <ModalSection title="Decision">
                <p className="action-approval-section__lead">Choose the next workflow step for this action.</p>
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
                        <span className="action-approval-status-card__icon-wrap" aria-hidden>
                          <Icon size={16} />
                        </span>
                        <span className="action-approval-status-card__copy">
                          <span className="action-approval-status-card__label">{option.label}</span>
                          <span className="action-approval-status-card__desc">{option.description}</span>
                        </span>
                        {isCurrent && <span className="action-approval-status-card__badge">Current</span>}
                      </button>
                    );
                  })}
                </div>

                <div className="action-approval-fields">
                  <label className="action-approval-owner-field">
                    <span className="action-approval-owner-field__label">Owner</span>
                    <div className="action-approval-owner-field__control">
                      <User size={15} aria-hidden className="action-approval-owner-field__icon" />
                      <input
                        type="text"
                        className="form-input action-approval-owner-field__input"
                        value={owner}
                        onChange={(e) => setOwner(e.target.value)}
                        placeholder="Optional"
                        aria-label="Action owner"
                      />
                    </div>
                  </label>
                  <label className="action-approval-note-field">
                    <span className="action-approval-note-field__label">Note</span>
                    <textarea
                      className="form-textarea action-approval-note"
                      rows={3}
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder={
                        noteRequired
                          ? 'Required for reject or defer'
                          : 'Optional audit note'
                      }
                      aria-invalid={noteRequired && !note.trim()}
                    />
                  </label>
                </div>

                {noteRequired && !note.trim() && (
                  <p className="action-approval-note__hint">Add a note when rejecting or deferring.</p>
                )}
              </ModalSection>
            )}

            <CollapsibleSection title="Activity" defaultOpen={false}>
              <WorkflowHistory history={action.workflow_history} />
            </CollapsibleSection>
          </div>

          <footer className="action-approval-modal__footer">
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClose} disabled={isPending}>
              Cancel
            </button>
            {isAdmin ? (
              <button
                type="button"
                className={`btn btn-primary btn-sm action-approval-modal__submit action-approval-modal__submit--${selectedOption?.tone || 'approved'}`}
                disabled={!canSubmit}
                onClick={handleSubmit}
              >
                {isPending ? 'Saving…' : (selectedOption?.cta || 'Save changes')}
              </button>
            ) : (
              <button type="button" className="btn btn-primary btn-sm" onClick={onClose}>
                Close
              </button>
            )}
          </footer>
        </div>
      </div>
    </ModalPortal>
  );
}
