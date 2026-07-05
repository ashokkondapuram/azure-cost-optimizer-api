import React from 'react';
import FindingsBadge from '../FindingsBadge';

/** Table-friendly findings badge with consistent inline layout. */
export default function InlineFindingBadge(props) {
  return (
    <span className="inline-finding-badge">
      <FindingsBadge {...props} compact />
    </span>
  );
}
