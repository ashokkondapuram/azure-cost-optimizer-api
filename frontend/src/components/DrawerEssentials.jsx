import React from 'react';
import ArmResourceLink from './ArmResourceLink';
import { isArmResourceId } from '../utils/armResourceLinks';
import { isMajorProperty } from '../utils/insightCanvasUtils';

/**
 * Azure portal–style essentials list (label / value rows, not tiles).
 */
export default function DrawerEssentials({
  rows = [],
  title = 'Essentials',
  className = '',
  hideTitle = false,
}) {
  if (!rows.length) return null;

  return (
    <section
      className={`insight-drawer__essentials${className ? ` ${className}` : ''}`}
      aria-label={title}
    >
      {!hideTitle && (
        <h4 className="insight-drawer__essentials-title">{title}</h4>
      )}
      <dl className="insight-drawer__essentials-list">
        {rows.map((row) => {
          const valueText = row.value != null ? String(row.value) : '—';
          return (
            <div
              key={row.key}
              className={[
                'insight-drawer__essentials-row',
                row.tone ? `insight-drawer__essentials-row--${row.tone}` : '',
                row.fullWidth ? 'insight-drawer__essentials-row--full' : '',
                isMajorProperty({ label: row.label, fact_key: row.fact_key || row.key })
                  ? 'insight-drawer__essentials-row--major'
                  : '',
              ].filter(Boolean).join(' ')}
            >
              <dt className="insight-drawer__essentials-label">{row.label}</dt>
              <dd className="insight-drawer__essentials-value" title={row.render ? undefined : valueText}>
                <EssentialValue row={row} />
              </dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
}

function EssentialValue({ row }) {
  if (row.render) return row.render;
  if (row.linkResourceId && isArmResourceId(row.linkResourceId)) {
    return <ArmResourceLink resourceId={row.linkResourceId} showFullId={row.showFullId} />;
  }
  if (row.href) {
    return (
      <a href={row.href} target="_blank" rel="noopener noreferrer" className="insight-drawer__essentials-link">
        {row.value}
      </a>
    );
  }
  return row.value ?? '—';
}
