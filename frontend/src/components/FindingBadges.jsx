import React from 'react';
import { SeverityIcon, StatusIcon, IconChip, CATEGORY_META } from './FinOpsIcons';
import { iconForCategory } from '../config/assetIcons';

const SEV_CLASS = {
  CRITICAL: 'badge badge-critical',
  HIGH: 'badge badge-high',
  MEDIUM: 'badge badge-medium',
  LOW: 'badge badge-low',
  INFO: 'badge badge-info',
};

export function SeverityBadge({ severity, size = 12 }) {
  return (
    <span className={`${SEV_CLASS[severity] || 'badge'} badge--with-icon`}>
      <SeverityIcon severity={severity} size={size} />
      {severity}
    </span>
  );
}

export function CategoryBadge({ category, size = 11 }) {
  const meta = CATEGORY_META[(category || '').toUpperCase()];
  return (
    <span className="badge badge-info badge--with-icon">
      {meta ? (
        <IconChip Icon={meta.Icon} color={meta.color} size={size} iconKey={iconForCategory(category)} />
      ) : null}
      {category}
    </span>
  );
}

export function StatusBadge({ status, size = 12 }) {
  const statusClass =
    status === 'resolved' ? 'badge-low'
      : status === 'acknowledged' ? 'badge-medium'
      : status === 'ignored' ? 'badge-info'
      : 'badge-high';

  return (
    <span className={`badge badge--with-icon ${statusClass}`}>
      <StatusIcon status={status} size={size} />
      {status}
    </span>
  );
}
