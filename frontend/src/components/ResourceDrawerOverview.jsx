import React, { useMemo } from 'react';
import { getDrawerOverviewTiles } from '../utils/resourceDrawerUtils';

export default function ResourceDrawerOverview({ resource, compact = false }) {
  const tiles = useMemo(
    () => getDrawerOverviewTiles(resource),
    [resource],
  );

  if (!tiles.length) return null;

  return (
    <div
      className={`insight-drawer__overview-grid${compact ? ' insight-drawer__overview-grid--compact' : ''}`}
      role="list"
    >
      {tiles.map((tile) => (
        <div
          key={tile.key}
          role="listitem"
          className="insight-drawer__overview-tile"
        >
          <span className="insight-drawer__overview-label">
            {tile.label}
          </span>
          <span className="insight-drawer__overview-value">{tile.value}</span>
        </div>
      ))}
    </div>
  );
}
