import React from 'react';

export default function DrawerCollapseControls({
  expanded,
  onToggle,
  itemCount = 0,
  collapseLabel = 'Collapse all',
  expandLabel = 'Expand all',
}) {
  if (!itemCount) return null;
  return (
    <div className="drawer-collapse-controls">
      <button
        type="button"
        className="drawer-collapse-controls__btn"
        onClick={onToggle}
        aria-expanded={expanded}
      >
        {expanded ? collapseLabel : expandLabel}
      </button>
      <span className="drawer-collapse-controls__count">{itemCount} items</span>
    </div>
  );
}
