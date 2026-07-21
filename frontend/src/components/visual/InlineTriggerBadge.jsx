import React from 'react';
import { Activity } from 'lucide-react';
import {
  countTriggerMetricsForFindings,
  primaryTriggerLabel,
} from '../../utils/triggerUtils';

export default function InlineTriggerBadge({
  findings = [],
  indexReady = true,
  compact = false,
}) {
  if (!indexReady) {
    return <span className="resource-table__empty" title="Loading cost signals">…</span>;
  }

  const count = countTriggerMetricsForFindings(findings);
  if (!count) {
    return <span className="resource-table__empty" title="No cost signals from open findings">—</span>;
  }

  const primary = primaryTriggerLabel(findings);
  const title = primary
    ? `${count} cost signal${count === 1 ? '' : 's'} · ${primary}`
    : `${count} cost signal${count === 1 ? '' : 's'}`;

  return (
    <span className={`inline-trigger-badge${compact ? ' inline-trigger-badge--compact' : ''}`} title={title}>
      <Activity size={12} aria-hidden />
      <span className="inline-trigger-badge__count">{count}</span>
      {!compact && primary && (
        <span className="inline-trigger-badge__label">{primary}</span>
      )}
    </span>
  );
}
