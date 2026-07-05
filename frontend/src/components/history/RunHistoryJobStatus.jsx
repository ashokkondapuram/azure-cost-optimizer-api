import React from 'react';
import { formatCurrency } from '../../utils/format';
import { componentStatusLabel, jobStatusLabel, jobStatusTone } from '../../utils/runHistoryUtils';

function ComponentStatusGrid({ components = [], currency = 'CAD' }) {
  if (!components.length) return null;
  return (
    <div className="run-history-job-status">
      <h4 className="run-history-job-status__title">Job steps</h4>
      <div className="batch-components-grid run-history-job-status__grid">
        {components.map((component) => {
          const status = component.status || 'pending';
          return (
            <div
              key={component.component}
              className={`batch-comp batch-comp--${status}`}
            >
              <div className="batch-comp__head">
                <span className="batch-comp__name">{component.component}</span>
                <span className={`badge badge-${jobStatusTone(status === 'completed' ? 'completed' : status === 'failed' ? 'failed' : status === 'running' ? 'running' : 'queued')}`}>
                  {componentStatusLabel(component)}
                </span>
              </div>
              <span className="batch-comp__meta">
                {status === 'completed'
                  ? `${component.findings ?? 0} findings · ${formatCurrency(component.savings_usd || 0, { currency })}`
                  : (component.error || status)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function RunHistoryJobStatus({ job, currency = 'CAD' }) {
  if (!job) return null;
  const status = job.status || 'completed';
  return (
    <section className="run-history-job-status" aria-label="Analysis job status">
      <header className="run-history-job-status__header">
        <h4 className="run-history-job-status__title">Job status</h4>
        <span className={`badge badge-${jobStatusTone(status)}`}>
          {jobStatusLabel(status, job.status_label)}
        </span>
        {job.progress_pct != null && status === 'running' && (
          <span className="run-history-job-status__progress">{job.progress_pct}%</span>
        )}
      </header>
      {job.scope_label && (
        <p className="run-history-job-status__scope">Scope: {job.scope_label}</p>
      )}
      {job.error_message && (
        <p className="run-history-job-status__error" role="alert">{job.error_message}</p>
      )}
      <ComponentStatusGrid components={job.components} currency={currency} />
    </section>
  );
}
