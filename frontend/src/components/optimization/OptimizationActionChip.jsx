import React from 'react';
import { actionTypeLabel } from '../../utils/actionUtils';

const ACTION_TONES = {
  resize_down: 'cost',
  downgrade_disk: 'cost',
  buy_reservation: 'cost',
  investigate: 'info',
  manual_review: 'warn',
  keep: 'muted',
};

export default function OptimizationActionChip({ actionType, compact = false }) {
  if (!actionType) return <span className="text-muted">—</span>;
  const tone = ACTION_TONES[actionType] || 'info';
  return (
    <span className={`action-chip action-chip--${tone}${compact ? ' action-chip--compact' : ''}`}>
      {actionTypeLabel(actionType)}
    </span>
  );
}
