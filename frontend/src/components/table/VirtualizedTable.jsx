import React from 'react';
import { FixedSizeList as List } from 'react-window';

const DEFAULT_HEIGHT = 520;
const DEFAULT_ROW_HEIGHT = 48;

/**
 * Virtualized scroll region for large tables and lists.
 * @param {{
 *   items: unknown[],
 *   height?: number,
 *   rowHeight?: number,
 *   className?: string,
 *   header?: React.ReactNode,
 *   children: (item: unknown, index: number) => React.ReactNode,
 * }} props
 */
export default function VirtualizedTable({
  items,
  height = DEFAULT_HEIGHT,
  rowHeight = DEFAULT_ROW_HEIGHT,
  className = '',
  header = null,
  children,
}) {
  if (!items?.length) return null;

  const Row = ({ index, style }) => (
    <div className="virtual-table__row" style={style} role="row">
      {children(items[index], index)}
    </div>
  );

  return (
    <div className={`virtual-table${className ? ` ${className}` : ''}`}>
      {header && <div className="virtual-table__head">{header}</div>}
      <List
        className="virtual-table__body"
        height={Math.min(height, Math.max(rowHeight, items.length * rowHeight))}
        itemCount={items.length}
        itemSize={rowHeight}
        width="100%"
        overscanCount={8}
      >
        {Row}
      </List>
    </div>
  );
}
