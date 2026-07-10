import React from 'react';
import { Info } from 'lucide-react';

/**
 * Explains what a savings headline measures — shown below hero title/subtitle.
 */
export default function SavingsScopeNote({ title, description, className = '' }) {
  if (!title && !description) return null;

  return (
    <p
      className={`savings-scope-note${className ? ` ${className}` : ''}`}
      role="note"
    >
      <Info size={14} className="savings-scope-note__icon" aria-hidden />
      <span>
        {title ? <strong>{title}. </strong> : null}
        {description}
      </span>
    </p>
  );
}
