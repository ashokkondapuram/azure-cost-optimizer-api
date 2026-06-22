import React from 'react';
export default function CostBadge({ value }) {
  const color = value > 800 ? '#c0392b' : value > 300 ? '#d67f00' : '#107c10';
  const bg    = value > 800 ? '#fde7e9' : value > 300 ? '#fff4ce' : '#dff6dd';
  return (
    <span style={{ fontWeight:700, color, background:bg,
      padding:'3px 9px', borderRadius:6, fontSize:'0.82rem' }}>
      ${value.toLocaleString()}
    </span>
  );
}
