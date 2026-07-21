import React from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw, Clock, Activity } from 'lucide-react';
import { formatCurrency, formatDateTime } from '../../utils/format';

function formatElapsed(seconds) {
  if (seconds == null || seconds < 0) return null;
  if (seconds < 60) return `${seconds}s`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins < 60) return `${mins}m ${secs}s`;
  const hours = Math.floor(mins / 60);
  const remMins = mins % 60;
  return `${hours}h ${remMins}m`;
}

function statusTone(status) {
  if (status === 'running') return 'info';
  if (status === 'queued') return 'medium';
  if (status === 'completed') return 'low';
  if (status === 'failed') return 'critical';
  return 'medium';
}

function stepMessage(job) {
  if (job.current_step || job.current_component) {
    return job.current_step || job.current_component;
  }
  if (job.status === 'queued') return 'Waiting to start…';
  if (job.status === 'completed') return 'Analysis finished.';
  if (job.status === 'failed') return job.error_message || 'Analysis failed.';
  return 'Preparing…';
}

export default function AnalysisJobProgress({
  job,
  onRefresh,
  onCancel,
  currency = 'CAD',
  variant = 'default',
  onOpenRun,
}) {
  if (!job) return null;

  const isActive = job.is_active || job.status === 'queued' || job.status === 'running';
  const elapsed = formatElapsed(job.elapsed_seconds);
  const statusLabel = job.status_label || job.status;
  const showCancel = isActive && typeof onCancel === 'function';

  return (
    <section
      className={`analysis-job-panel card${variant === 'history' ? ' analysis-job-panel--history' : ''}`}
      aria-live="polite"
      aria-busy={isActive ? 'true' : undefined}
    >
      <header className="analysis-job-panel__header">
        <div className="analysis-job-panel__title-row">
          <Activity size={16} aria-hidden />
          <strong>{isActive ? 'Analysis in progress' : 'Latest analysis job'}</strong>
          <span className={`badge badge-${statusTone(job.status)}`}>{statusLabel}</span>
        </div>
        {isActive && onRefresh && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onRefresh}>
            <RefreshCw size={14} /> Refresh
          </button>
        )}
        {showCancel && (
          <button type="button" className="btn btn-ghost btn-sm" onClick={onCancel}>
            Cancel
          </button>
        )}
      </header>

      <div className="analysis-job-panel__body">
        <div
          className="progress-bar analysis-job-panel__progress"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={job.progress_pct || 0}
          aria-label={`Analysis progress ${job.progress_pct || 0}%`}
        >
          <div
            className="progress-bar__fill"
            style={{ width: `${Math.max(job.progress_pct || 0, isActive ? 4 : 0)}%` }}
          />
        </div>

        <p className="analysis-job-panel__step">{stepMessage(job)}</p>

        <dl className="analysis-job-panel__meta">
          <div>
            <dt>Scope</dt>
            <dd>{job.scope_label || 'Full analysis'}</dd>
          </div>
          <div>
            <dt>Engine</dt>
            <dd>{job.engine_version || 'extended'}</dd>
          </div>
          <div>
            <dt>Profile</dt>
            <dd>{job.profile || 'default'}</dd>
          </div>
          {job.started_at && (
            <div>
              <dt>Started</dt>
              <dd>{formatDateTime(job.started_at)}</dd>
            </div>
          )}
          {elapsed && (
            <div>
              <dt>Elapsed</dt>
              <dd><Clock size={12} aria-hidden /> {elapsed}</dd>
            </div>
          )}
          {!isActive && job.completed_at && (
            <div>
              <dt>Finished</dt>
              <dd>{formatDateTime(job.completed_at)}</dd>
            </div>
          )}
        </dl>

        {Array.isArray(job.components) && job.components.length > 0 && (
          <div className="batch-components-grid analysis-job-panel__components">
            {job.components.map((c) => (
              <div key={c.component} className={`batch-comp batch-comp--${c.status || 'pending'}`}>
                <span className="batch-comp__name">{c.component}</span>
                <span className="batch-comp__meta">
                  {c.status === 'completed'
                    ? `${c.findings} findings · ${formatCurrency(c.savings_usd || 0, { currency })}`
                    : c.status || 'pending'}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="analysis-job-panel__footer">
          <span className="analysis-job-panel__job-id" title={job.id}>
            Job {job.id.slice(0, 8)}…
          </span>
          {job.run_id && !isActive && (
            onOpenRun ? (
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => onOpenRun(job.run_id)}>
                View run
              </button>
            ) : (
              <Link to={`/history?run=${job.run_id}`} className="btn btn-ghost btn-sm">
                View run
              </Link>
            )
          )}
        </div>

        {job.status === 'failed' && job.error_message && (
          <p className="analysis-job-panel__error" role="alert">{job.error_message}</p>
        )}
      </div>
    </section>
  );
}
