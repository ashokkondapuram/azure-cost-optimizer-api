import React from 'react';
const CFG = {
  prod:    { label:'Production', bg:'#fde7e9', color:'#c0392b', dot:'#c0392b' },
  staging: { label:'Staging',    bg:'#fff4ce', color:'#d67f00', dot:'#d67f00' },
  dev:     { label:'Dev',        bg:'#dff6dd', color:'#107c10', dot:'#107c10' },
};
export default function EnvBadge({ env }) {
  const c = CFG[env] || CFG['dev'];
  return (
    <span style={{ display:'inline-flex', alignItems:'center', gap:5,
      background:c.bg, color:c.color, padding:'3px 9px',
      borderRadius:20, fontSize:'0.7rem', fontWeight:700 }}>
      <span style={{ width:6, height:6, borderRadius:'50%', background:c.dot }} />
      {c.label}
    </span>
  );
}
