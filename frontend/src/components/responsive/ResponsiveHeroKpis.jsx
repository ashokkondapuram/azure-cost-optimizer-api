import React from 'react';

/** Stacks hero KPI metrics vertically on narrow viewports. */
export default function ResponsiveHeroKpis({ className = '', children }) {
  return (
    <div className={`responsive-hero-kpis${className ? ` ${className}` : ''}`}>
      {children}
    </div>
  );
}
