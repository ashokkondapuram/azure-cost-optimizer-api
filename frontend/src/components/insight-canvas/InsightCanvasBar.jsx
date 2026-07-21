import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import AssetIcon from '../AssetIcon';
import ActionWorkflowNoteModal from '../optimization/ActionWorkflowNoteModal';
import useActionWorkflowUpdate from '../../hooks/useActionWorkflowUpdate';

function ChevronLeft() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16" aria-hidden="true">
      <polyline points="15 18 9 12 15 6" />
    </svg>
  );
}

function ChevronRight() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width="16" height="16" aria-hidden="true">
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

function pickWorkflowAction(actions = [], workflowKey = 'proposed') {
  return actions.find((a) => (a.workflow_status || 'proposed') === workflowKey)
    || actions.find((a) => (a.workflow_status || 'proposed') === 'proposed')
    || actions[0]
    || null;
}

export default function InsightCanvasBar({
  data,
  positionLabel,
  onPrev,
  onNext,
  prevDisabled,
  nextDisabled,
  subscriptionId,
  isAdmin,
}) {
  const [noteStatus, setNoteStatus] = useState(null);
  const { updateAction, isPending, pendingActionId } = useActionWorkflowUpdate(subscriptionId);

  const workflowKey = data?.workflowKey || 'proposed';
  const primaryLabel = workflowKey === 'approved' ? 'Execute' : 'Approve';
  const primaryTargetStatus = workflowKey === 'approved' ? 'executed' : 'approved';

  const action = useMemo(
    () => pickWorkflowAction(data?.actions, workflowKey),
    [data?.actions, workflowKey],
  );

  const isRowPending = isPending && pendingActionId === action?.id;
  const resourceId = data?.row?.id || data?.finding?.resource_id;

  const submitUpdate = (body, onSuccess) => {
    if (!action?.id) return;
    updateAction(action.id, body, { onSuccess });
  };

  const handlePrimary = () => {
    if (!action?.id || !isAdmin) {
      window.alert(`${primaryLabel} action (prototype)`);
      return;
    }
    submitUpdate({ workflow_status: primaryTargetStatus });
  };

  const handleDismiss = () => {
    if (!action?.id || !isAdmin) {
      window.alert('Dismiss action (prototype)');
      return;
    }
    setNoteStatus('rejected');
  };

  return (
    <header className="ic-bar">
      <div className="ic-bar__row">
        <Link to="/action-centre" className="ic-bar__back" aria-label="Back to Action centre">
          <ChevronLeft />
          <span>Action centre</span>
        </Link>
        <span className="ic-bar__divider" aria-hidden="true" />
        <div className="ic-bar__identity">
          <AssetIcon iconKey={data?.iconKey} size={40} className="ic-bar__icon resource-icon" />
          <div className="ic-bar__titles">
            <h1 className="ic-bar__title">{data?.title}</h1>
            <p className="ic-bar__subtitle">
              <span>{data?.type}</span>
              <span className="ic-bar__dot" aria-hidden="true">·</span>
              <span>{data?.rg}</span>
              <span className="ic-bar__dot" aria-hidden="true">·</span>
              <span>{data?.sub}</span>
            </p>
          </div>
        </div>
        <span className="ic-bar__divider" aria-hidden="true" />
        <div className="ic-bar__status">
          <span className={`sev sev-${data?.severityKey}`}>{data?.severity}</span>
          <span className={`workflow-badge workflow-badge--${data?.workflowKey}`}>{data?.workflow}</span>
        </div>
        <span className="ic-bar__divider" aria-hidden="true" />
        <div className="ic-bar__nav" aria-label="Navigate findings">
          <button
            type="button"
            className="ic-bar__nav-btn"
            aria-label="Previous finding"
            onClick={onPrev}
            disabled={prevDisabled}
          >
            <ChevronLeft />
          </button>
          <span className="ic-bar__nav-pos">{positionLabel}</span>
          <button
            type="button"
            className="ic-bar__nav-btn"
            aria-label="Next finding"
            onClick={onNext}
            disabled={nextDisabled}
          >
            <ChevronRight />
          </button>
        </div>
        <div className="ic-bar__actions">
          {resourceId && (
            <a
              className="btn btn-ghost btn-sm"
              href={`https://portal.azure.com/#resource${resourceId}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              View in Azure
            </a>
          )}
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={handleDismiss}
            disabled={isRowPending}
          >
            Dismiss
          </button>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={handlePrimary}
            disabled={isRowPending}
          >
            {primaryLabel}
          </button>
        </div>
      </div>

      {noteStatus && (
        <ActionWorkflowNoteModal
          status={noteStatus}
          isPending={isRowPending}
          onClose={() => setNoteStatus(null)}
          onSubmit={(body) => submitUpdate(body, () => setNoteStatus(null))}
        />
      )}
    </header>
  );
}
