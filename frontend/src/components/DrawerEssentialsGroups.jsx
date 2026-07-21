import React from 'react';
import DrawerEssentials from './DrawerEssentials';

/**
 * Responsive grid of property group cards (Identity, Status, Configuration, …).
 */
export default function DrawerEssentialsGroups({ groups = [] }) {
  if (!groups.length) return null;

  return (
    <div className="insight-drawer__essentials-groups insight-drawer__essentials-groups--compact">
      {groups.map((group) => (
        <DrawerEssentials
          key={group.id}
          rows={group.rows}
          title={group.label}
          hideTitle={group.flat || !group.label}
          className={[
            'insight-drawer__essentials--group-card',
            group.spanFull ? 'insight-drawer__essentials--group-card--span-full' : '',
            group.flat ? 'insight-drawer__essentials--group-card--flat' : '',
          ].filter(Boolean).join(' ')}
        />
      ))}
    </div>
  );
}
