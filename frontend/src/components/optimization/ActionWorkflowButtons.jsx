import React, { useState } from 'react';
import ActionWorkflowNoteModal from './ActionWorkflowNoteModal';
import useActionWorkflowUpdate from '../../hooks/useActionWorkflowUpdate';
import { quickWorkflowOptions } from '../../utils/workflowOptions';

export default function ActionWorkflowButtons({
  action,
  subscriptionId,
  isAdmin = false,
  currency = 'CAD',
  variant = 'compact',
  className = '',
  onUpdated,
}) {
  const [noteStatus, setNoteStatus] = useState(null);
  const { updateAction, isPending, pendingActionId } = useActionWorkflowUpdate(subscriptionId);

  if (!action?.id) return null;

  const currentStatus = action.workflow_status || 'proposed';
  const options = quickWorkflowOptions({ isAdmin, currentStatus });
  const isRowPending = isPending && pendingActionId === action.id;

  const submitUpdate = (body, onSuccess) => {
    updateAction(action.id, body, {
      onSuccess: () => {
        setNoteStatus(null);
        onUpdated?.(body);
        onSuccess?.();
      },
    });
  };

  const handleQuickAction = (option) => {
    if (option.noteRequired) {
      setNoteStatus(option.value);
      return;
    }
    submitUpdate({ workflow_status: option.value });
  };

  if (!options.length) return null;

  return (
    <>
      <div
        className={`action-workflow-buttons action-workflow-buttons--${variant}${className ? ` ${className}` : ''}`}
        onClick={(event) => event.stopPropagation()}
        role="group"
        aria-label="Workflow actions"
      >
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            className={`btn btn-ghost btn-sm action-workflow-buttons__btn action-workflow-buttons__btn--${option.tone}`}
            disabled={isRowPending}
            onClick={() => handleQuickAction(option)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {noteStatus && (
        <ActionWorkflowNoteModal
          status={noteStatus}
          isPending={isRowPending}
          onClose={() => setNoteStatus(null)}
          onSubmit={(body) => submitUpdate(body)}
        />
      )}
    </>
  );
}
