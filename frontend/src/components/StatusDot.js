import React from 'react';
const COLORS = {
  Running:'#107c10', Active:'#107c10', Online:'#107c10', Associated:'#107c10',
  Stopped:'#c0392b', Unattached:'#d67f00', Unassigned:'#d67f00', Unknown:'#9ba3b8'
};
export default function StatusDot({ status }) {
  const c = COLORS[status] || '#9ba3b8';
  return (
    <span style={{ display:'inline-flex', alignItems:'center', gap:5, fontSize:'0.78rem', fontWeight:600, color:c }}>
      <span style={{ width:7, height:7, borderRadius:'50%', background:c, flexShrink:0,
        boxShadow: c==='#107c10' ? '0 0 0 3px rgba(16,124,16,0.15)' : 'none' }} />
      {status}
    </span>
  );
}
