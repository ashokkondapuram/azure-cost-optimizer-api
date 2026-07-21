import React from 'react';
import { toDisplayText } from '../utils/formatDisplay';

/** Inline status message for sync / analysis actions. */
export default function ActionMessage({ message, className = 'analysis-bar__msg' }) {
  if (message == null || message === '') return null;
  const text = toDisplayText(message);
  if (text === '—') return null;
  const ok = text.startsWith('Synced') || text.startsWith('Fetched') || text.startsWith('Loaded') || text.startsWith('Imported') || text.startsWith('\u2713');
  return (
    <span className={`${className} ${ok ? 'analysis-bar__msg--ok' : 'analysis-bar__msg--err'}`}>
      {text}
    </span>
  );
}
