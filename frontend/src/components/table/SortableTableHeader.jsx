import React from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';

/**
 * Clickable table header cell with sort direction indicator.
 * @param {{ sortKey: string, activeKey: string|null, direction: 'asc'|'desc', onSort: (key: string) => void, children: React.ReactNode, className?: string }} props
 */
export default function SortableTableHeader({
  sortKey,
  activeKey,
  direction = 'asc',
  onSort,
  children,
  className = '',
}) {
  const isActive = activeKey === sortKey;
  const Icon = !isActive ? ArrowUpDown : (direction === 'asc' ? ArrowUp : ArrowDown);

  return (
    <th className={className}>
      <button
        type="button"
        className={`sortable-th${isActive ? ' sortable-th--active' : ''}`}
        onClick={() => onSort(sortKey)}
      >
        <span>{children}</span>
        <Icon size={14} aria-hidden />
      </button>
    </th>
  );
}
