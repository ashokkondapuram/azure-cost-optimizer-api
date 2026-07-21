import React from 'react';
import { toDisplayText } from '../utils/formatDisplay';

/** Ordered steps for proposed optimization actions. */
export default function ImplementationSteps({
  steps,
  className = '',
  defaultOpen = false,
  inline = false,
}) {
  if (!steps?.length) return null;

  if (inline) {
    return (
      <div className={`implementation-steps implementation-steps--inline${className ? ` ${className}` : ''}`}>
        <h4 className="implementation-steps__heading">Implementation steps</h4>
        <ol className="implementation-steps__list">
          {steps.map((step, idx) => (
            <li key={`step-${idx}`}>{toDisplayText(step)}</li>
          ))}
        </ol>
      </div>
    );
  }

  return (
    <details className={`implementation-steps${className ? ` ${className}` : ''}`} open={defaultOpen || undefined}>
      <summary className="implementation-steps__summary">Implementation steps</summary>
      <ol className="implementation-steps__list">
        {steps.map((step, idx) => (
          <li key={`step-${idx}`}>{toDisplayText(step)}</li>
        ))}
      </ol>
    </details>
  );
}
