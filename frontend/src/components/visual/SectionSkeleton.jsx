import React from 'react';

export default function SectionSkeleton({ rows = 3 }) {
  return (
    <div className="section-skeleton">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="section-skeleton__row">
          <div className="section-skeleton__line section-skeleton__line--header" />
          <div className="section-skeleton__line" />
          <div className="section-skeleton__line section-skeleton__line--short" />
        </div>
      ))}
    </div>
  );
}
