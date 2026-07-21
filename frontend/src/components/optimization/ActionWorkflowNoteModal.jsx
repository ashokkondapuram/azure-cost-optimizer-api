import React, { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import ModalPortal from '../ModalPortal';
import { workflowOptionForStatus } from '../../utils/workflowOptions';

export default function ActionWorkflowNoteModal({
  status,
  isPending = false,
  onClose,
  onSubmit,
}) {
  const [note, setNote] = useState('');
  const dialogRef = useRef(null);
  const option = workflowOptionForStatus(status);

  useEffect(() => {
    setNote('');
  }, [status]);

  useEffect(() => {
    if (!status) return undefined;
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
  }, [status, isPending, onClose]);

  if (!status || !option) return null;

  const canSubmit = note.trim().length > 0 && !isPending;

  return (
    <ModalPortal>
      <div className="modal-overlay action-workflow-note-overlay" role="presentation" onClick={onClose}>
        <div
          ref={dialogRef}
          className="modal-card action-workflow-note-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="action-workflow-note-title"
          tabIndex={-1}
          onClick={(e) => e.stopPropagation()}
        >
          <header className="action-workflow-note-modal__header">
            <h2 id="action-workflow-note-title" className="action-workflow-note-modal__title">
              {option.cta}
            </h2>
            <button
              type="button"
              className="btn-icon action-workflow-note-modal__close"
              onClick={onClose}
              aria-label="Close"
            >
              <X size={18} />
            </button>
          </header>
          <p className="action-workflow-note-modal__lead">
            Add a note explaining why you are {option.label.toLowerCase()}ing this action.
          </p>
          <label className="action-workflow-note-modal__field">
            <span className="action-workflow-note-modal__label">Note</span>
            <textarea
              className="form-textarea action-workflow-note-modal__textarea"
              rows={4}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Required"
              aria-invalid={!note.trim()}
              autoFocus
            />
          </label>
          <footer className="action-workflow-note-modal__footer">
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClose} disabled={isPending}>
              Cancel
            </button>
            <button
              type="button"
              className={`btn btn-primary btn-sm action-workflow-note-modal__submit action-workflow-note-modal__submit--${option.tone}`}
              disabled={!canSubmit}
              onClick={() => onSubmit({ workflow_status: status, note: note.trim() })}
            >
              {isPending ? 'Saving…' : option.cta}
            </button>
          </footer>
        </div>
      </div>
    </ModalPortal>
  );
}
