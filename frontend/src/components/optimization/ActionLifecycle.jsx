import React from 'react';
import { formatCurrency } from '../../utils/format';

const STEPS = [
  { id: 'proposed', label: 'Proposed', filter: 'proposed' },
  { id: 'approved', label: 'Approved', filter: 'approved' },
  { id: 'executed', label: 'Executed', filter: 'executed' },
  { id: 'rejected', label: 'Rejected', filter: 'rejected' },
  { id: 'deferred', label: 'Deferred', filter: 'deferred' },
];

function ExecutionProgressRing({ executed, proposed }) {
  const executionRate = proposed > 0 ? (executed / proposed) * 100 : 0;
  const percentage = Math.round(executionRate);

  return (
    <div className="action-lifecycle-progress">
      <div className="action-lifecycle-progress__ring">
        <div className="action-lifecycle-progress__ring-bg" aria-hidden />
        <div
          className="action-lifecycle-progress__ring-fill"
          style={{ '--execution-rate': executionRate / 100 }}
          aria-hidden
        />
        <div className="action-lifecycle-progress__ring-value">
          {percentage}%
        </div>
      </div>
      <div className="action-lifecycle-progress__content">
        <div className="action-lifecycle-progress__label">
          Execution rate
        </div>
        <div className="action-lifecycle-progress__sub">
          {executed.toLocaleString()} of {proposed.toLocaleString()} actions completed
        </div>
      </div>
    </div>
  );
}

export default function ActionLifecycle({
  counts = {},
  inObservation = 0,
  currency = 'CAD',
  savings = 0,
  activeFilter = '',
  onStepClick,
  className = '',
  compact = false,
}) {
  const stepCounts = {
    proposed: counts.proposed ?? 0,
    approved: counts.approved ?? 0,
    executed: counts.executed ?? 0,
    rejected: counts.rejected ?? 0,
    deferred: counts.deferred ?? 0,
  };

  return (
    <section
      className={`action-lifecycle${compact ? ' action-lifecycle--compact' : ''}${className ? ` ${className}` : ''}`}
      aria-label="Action workflow"
    >
      {!compact && (
        <>
          <div className="action-lifecycle__header">
            <h3 className="action-lifecycle__title">Workflow</h3>
            {savings > 0 && (
              <span className="action-lifecycle__savings">
                {formatCurrency(savings, { currency, decimals: 0 })}/mo potential
              </span>
            )}
          </div>
          {stepCounts.proposed > 0 && (
            <ExecutionProgressRing
              executed={stepCounts.executed}
              proposed={stepCounts.proposed}
            />
          )}
        </>
      )}
      <ol className="action-lifecycle__steps">
        {STEPS.map((step, index) => {
          const count = stepCounts[step.id];
          const isActive = step.filter && activeFilter === step.filter;
          const content = (
            <>
              <span className="action-lifecycle__marker" aria-hidden>
                {index < STEPS.length - 1 && <span className="action-lifecycle__connector" />}
                <span className="action-lifecycle__dot" />
              </span>
              <span className="action-lifecycle__body">
                <strong className="action-lifecycle__count">{count.toLocaleString()}</strong>
                <span className="action-lifecycle__label">{step.label}</span>
              </span>
            </>
          );

          return (
            <li
              key={step.id}
              className={`action-lifecycle__step${isActive ? ' action-lifecycle__step--active' : ''}${count > 0 ? ' action-lifecycle__step--has-count' : ''}`}
            >
              {onStepClick ? (
                <button
                  type="button"
                  className="action-lifecycle__step-btn"
                  aria-pressed={isActive}
                  onClick={() => onStepClick(step.id, step.filter)}
                >
                  {content}
                </button>
              ) : content}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
