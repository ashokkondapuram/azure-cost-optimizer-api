import React from 'react';
import { useOperationProgress } from '../context/OperationProgressContext';
import { useAuth } from '../context/AuthContext';

export default function GlobalProgressBar() {
  const { isAdmin } = useAuth();
  const {
    syncing, syncLabel, job, isActive,
  } = useOperationProgress();

  if (!isAdmin || !isActive) return null;

  const jobRunning = job?.status === 'queued' || job?.status === 'running';
  const progress = job?.progress_pct || 0;
  const indeterminate = syncing || (jobRunning && progress < 5);
  const label = syncing
    ? syncLabel
    : job?.current_component
      ? `${job.current_component} (${job.completed_batches || 0}/${job.total_batches || 0})`
      : jobRunning
        ? 'Running analysis…'
        : '';

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
    </div>
  );
}
