import React from 'react';

export function DrawerSectionSkeleton({ rows = 3 }) {
  return (
    <div className="drawer-section-skeleton" aria-busy="true" aria-hidden>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="drawer-section-skeleton__line" />
      ))}
    </div>
  );
}

export default function DrawerBodySkeleton() {
  return (
    <div className="drawer-body-skeleton" aria-busy="true" aria-label="Loading resource details">
      <DrawerSectionSkeleton rows={4} />
      <DrawerSectionSkeleton rows={3} />
      <DrawerSectionSkeleton rows={2} />
    </div>
  );
}
