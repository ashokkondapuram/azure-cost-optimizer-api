import React from 'react';
import { formatCurrency } from '../../utils/format';

export default function ActionCentreIntelStrip({
  proposed,
  savings,
  critical,
  open,
  currency = 'CAD',
}) {
  return (
    <p className="ac-intel-strip" aria-live="polite">
      <span className="ac-intel-strip__seg">
        <strong>{proposed}</strong>
        {' '}
        proposed
      </span>
      <span className="ac-intel-strip__dot" aria-hidden="true">·</span>
      <span className="ac-intel-strip__seg ac-intel-strip__seg--savings">
        <strong>{formatCurrency(savings, { currency, decimals: 0 })}</strong>
        {' '}
        savings
      </span>
      <span className="ac-intel-strip__dot" aria-hidden="true">·</span>
      <span className="ac-intel-strip__seg ac-intel-strip__seg--critical">
        <strong>{critical}</strong>
        {' '}
        critical
      </span>
      <span className="ac-intel-strip__dot" aria-hidden="true">·</span>
      <span className="ac-intel-strip__seg">
        <strong>{open}</strong>
        {' '}
        open
      </span>
    </p>
  );
}
