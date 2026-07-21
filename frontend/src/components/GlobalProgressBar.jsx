import React, { useState } from 'react';
import { useOperationProgress } from '../context/OperationProgressContext';
import { useAuth } from '../context/AuthContext';
import { pipelineStageLabel } from '../utils/syncPipelineUtils';

export default function GlobalProgressBar() {
  const { isAdmin } = useAuth();
  const {
    syncing, syncLabel, pipeline, pipelineActive, job, isActive, cancelActiveWork,
  } = useOperationProgress();
  const [cancelling, setCancelling] = useState(false);

  if (!isAdmin || !isActive) return null;

  const jobRunning = job?.status === 'queued' || job?.status === 'running';
  const pipelineProgress = pipeline?.progress_pct || 0;
  const progress = pipelineActive ? pipelineProgress : (job?.progress_pct || 0);
  const indeterminate = (syncing && !pipelineActive) || (jobRunning && progress < 5);
  const label = pipelineActive
    ? `${pipelineStageLabel(pipeline?.current_stage)} (${progress}%)`
    : syncing
      ? syncLabel
      : job?.current_component
        ? `${job.current_component} (${job.completed_batches || 0}/${job.total_batches || 0})`
        : jobRunning
          ? 'Running analysis…'
          : syncLabel;

  const handleCancel = async () => {
    if (cancelling) return;
    setCancelling(true);
    try {
      await cancelActiveWork();
    } finally {
      setCancelling(false);
    }
  };

  return (
    <div
      className="global-progress"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={indeterminate ? undefined : progress}
      aria-label={label || 'Operation in progress'}
      aria-busy="true"
    >
      <div
        className={`global-progress__bar${indeterminate ? ' global-progress__bar--indeterminate' : ''}`}
        style={indeterminate ? undefined : { width: `${Math.max(progress, 4)}%` }}
      />
      {label && (
        <span className="global-progress__label">{label}</span>
      )}
      <button
        type="button"
        className="global-progress__cancel btn btn-ghost btn-sm"
        onClick={handleCancel}
        disabled={cancelling}
        aria-label="Cancel operation"
      >
        {cancelling ? 'Cancelling…' : 'Cancel'}
      </button>
    </div>
  );
}
