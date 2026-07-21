import React from 'react';
import { Play, Square, Circle, AlertTriangle, HelpCircle } from 'lucide-react';

const STATUS_ICONS = {
  running: Play,
  stopped: Square,
  deallocated: Circle,
  warning: AlertTriangle,
  unknown: HelpCircle,
};

function statusClass(status) {
  const s = String(status || '').toLowerCase();
  if (['running', 'active', 'online', 'associated', 'succeeded'].some((x) => s.includes(x))) {
    return 'running';
  }
  if (s.includes('deallocated')) {
    return 'deallocated';
  }
  if (['stopped', 'failed'].some((x) => s.includes(x))) {
    return 'stopped';
  }
  if (['unattached', 'unassigned', 'warning'].some((x) => s.includes(x))) {
    return 'warning';
  }
  return 'unknown';
}

export default function StatusDot({ status }) {
  const kind = statusClass(status);
  const Icon = STATUS_ICONS[kind];

  return (
    <span className={`status-dot status-dot--${kind}`}>
      <span className="status-dot__indicator" aria-hidden="true" />
      <Icon className="status-dot__icon" size={11} aria-hidden="true" />
      <span>{status}</span>
    </span>
  );
}
