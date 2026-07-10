import React from 'react';
import { toDisplayText } from '../utils/formatDisplay';

/**
 * Collapsible implementation steps — collapsed by default across resource insight drawers.
 */
export default function AiImplementationSteps({ steps, className = '' }) {
  if (!steps?.length) return null;

  return (
    <details className={`ai-implementation-steps${className ? ` ${className}` : ''}`}>
      <summary className="ai-implementation-steps__summary">Implementation steps</summary>
      <ol className="ai-implementation-steps__list">
        {steps.map((step, idx) => (
          <li key={`ai-step-${idx}`}>{toDisplayText(step)}</li>
        ))}
      </ol>
    </details>
  );
}
