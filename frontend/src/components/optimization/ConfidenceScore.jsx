import React from 'react';
import { confidenceTone } from '../../utils/actionUtils';

export default function ConfidenceScore({ confidence, compact = false }) {
  if (!confidence) return <span className="text-muted">—</span>;
  const tone = confidenceTone(confidence);
  return (
    <span
      className={`confidence-score confidence-score--${tone}${compact ? ' confidence-score--compact' : ''}`}
      title={`Confidence: ${confidence}`}
    >
      <span className="confidence-score__dot" aria-hidden />
      {confidence}
    </span>
  );
}
