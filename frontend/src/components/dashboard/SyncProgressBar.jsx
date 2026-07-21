import React from 'react';
import {
  PIPELINE_STAGES,
  resolveStageDotState,
  syncProgressStageLabel,
} from '../../utils/syncPipelineUtils';
import useSyncProgress from '../../hooks/useSyncProgress';

function StageDots({ pipeline, uiStatus }) {
  if (!pipeline?.stages) return null;

  return (
    <ol className="sync-progress-bar__stages" aria-label="Sync pipeline stages">
      {PIPELINE_STAGES.map((stage) => {
        const row = pipeline.stages[stage];
        const dotState = resolveStageDotState(stage, row, pipeline);
        const stageLabel = syncProgressStageLabel(stage, row, pipeline);
        return (
          <li
            key={stage}
            className={`sync-progress-bar__stage sync-progress-bar__stage--${dotState}`}
            title={stageLabel}
            aria-label={stageLabel}
          >
            <span className="sync-progress-bar__stage-dot" aria-hidden="true" />
          </li>
        );
      })}
      {uiStatus === 'failed' && (
        <span className="sync-progress-bar__failed-icon" aria-hidden="true">!</span>
      )}
    </ol>
  );
}

export default function SyncProgressBar({ subscriptionId, enabled = true }) {
  const {
    pipeline,
    uiStatus,
    progressPct,
    label,
    retryHint,
    visible,
  } = useSyncProgress(subscriptionId, { enabled });

  if (!visible || !subscriptionId) return null;

  const indeterminate = uiStatus === 'running' && progressPct < 1 && !pipeline?.current_stage;
  const barPct = uiStatus === 'completed'
    ? 100
    : Math.max(progressPct || 0, uiStatus === 'running' ? 4 : 0);
  const tone = uiStatus === 'failed'
    ? 'failed'
    : uiStatus === 'completed'
      ? 'completed'
      : 'running';

  return (
    <div
      className={`sync-progress-bar sync-progress-bar--${tone}`}
      role="group"
      aria-label="Sync pipeline progress"
      aria-live="polite"
      aria-busy={uiStatus === 'running' ? 'true' : undefined}
    >
      <div className="sync-progress-bar__head">
        <span className="sync-progress-bar__label">{label}</span>
        {!indeterminate && uiStatus !== 'idle' && (
          <span className="sync-progress-bar__pct" aria-hidden="true">
            {barPct}%
          </span>
        )}
      </div>

      <div
        className="sync-progress-bar__track progress-bar"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={indeterminate ? undefined : barPct}
        aria-label={label || 'Sync progress'}
      >
        <div
          className={`sync-progress-bar__fill progress-bar__fill${indeterminate ? ' sync-progress-bar__fill--indeterminate' : ''}`}
          style={indeterminate ? undefined : { width: `${barPct}%` }}
        />
      </div>

      {pipeline && (
        <StageDots pipeline={pipeline} uiStatus={uiStatus} />
      )}

      {uiStatus === 'failed' && retryHint && (
        <p className="sync-progress-bar__error" role="alert">
          {retryHint}
        </p>
      )}
    </div>
  );
}
