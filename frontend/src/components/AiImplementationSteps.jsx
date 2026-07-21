import React from 'react';
import { toDisplayText } from '../utils/formatDisplay';

/**
 * Implementation steps — expanded by default in proposed-action cards.
 */
export default function AiImplementationSteps({ steps, className = '', defaultOpen = false }) {
  if (!steps?.length) return null;

  return (
    <details
      className={`ai-implementation-steps${className ? ` ${className}` : ''}`}
      open={defaultOpen || undefined}
    >
      <summary className="ai-implementation-steps__summary text-label">Implementation steps</summary>
      <ol className="ai-implementation-steps__list text-body-medium">
        {steps.map((step, idx) => (
          <li key={`ai-step-${idx}`}>{toDisplayText(step)}</li>
        ))}
      </ol>
    </details>
  );
}
