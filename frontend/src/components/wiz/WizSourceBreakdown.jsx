import React from 'react';
import {
  openFindingsCount,
  sourceBreakdownOrdered,
  excludedFindingsSummary,
  resourcesWithFindings,
} from '../../utils/findingsSummaryUtils';

function formatSourceParts(items) {
  return items
    .filter((item) => item.count > 0)
    .map((item) => `${item.count.toLocaleString()} ${item.label.toLowerCase()}`)
    .join(' · ');
}

/** Inline source split for stat strips and banners. */
export function OpenIssuesSubline({ summary, truncated = false, loadedCount = null }) {
  const open = openFindingsCount(summary);
  const parts = sourceBreakdownOrdered(summary);
  const resources = resourcesWithFindings(summary);
  const excluded = excludedFindingsSummary(summary);

  if (!open && !excluded.total) return null;

  const segments = [];
  const sourceText = formatSourceParts(parts);
  if (sourceText) segments.push(sourceText);
  if (resources > 0) {
    segments.push(`${resources.toLocaleString()} resources`);
  }
  if (excluded.total > 0) {
    const hidden = [];
    if (excluded.metric_gaps > 0) {
      hidden.push(`${excluded.metric_gaps.toLocaleString()} metrics gaps`);
    }
    if (excluded.cost_export_only > 0) {
      hidden.push(`${excluded.cost_export_only.toLocaleString()} deleted resources`);
    }
    segments.push(`${hidden.join(', ')} not in Action centre`);
  }
  if (truncated && loadedCount != null && loadedCount < open) {
    segments.push(`loaded ${loadedCount.toLocaleString()} of ${open.toLocaleString()}`);
  }

  return segments.join(' · ');
}

/** Chip row for Action centre filters. */
export default function WizSourceBreakdown({ summary, activeKey = '', onSelect }) {
  const items = sourceBreakdownOrdered(summary);
  if (!items.length) return null;

  return (
    <div className="wiz-source-breakdown" role="group" aria-label="Open issues by source">
      {items.map((item) => {
        const active = activeKey === item.key;
        const Tag = onSelect ? 'button' : 'span';
        return (
          <Tag
            key={item.key}
            type={onSelect ? 'button' : undefined}
            className={`wiz-pill${active ? ' wiz-pill--ok' : ''}`}
            onClick={onSelect ? () => onSelect(item.key) : undefined}
          >
            {item.label}
            {' '}
            <span className="wiz-pill__count">{item.count.toLocaleString()}</span>
          </Tag>
        );
      })}
    </div>
  );
}
