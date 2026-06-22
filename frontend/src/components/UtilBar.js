import React from 'react';
export default function UtilBar({ pct, color = '#0078d4' }) {
  const bg = pct > 80 ? '#c0392b' : pct > 60 ? '#d67f00' : color;
  return (
    <div style={{ display:'flex', alignItems:'center', gap:8 }}>
      <div style={{ flex:1, background:'#f0f2f7', borderRadius:99, height:6, overflow:'hidden' }}>
        <div style={{ width:`${pct}%`, background:bg, height:'100%', borderRadius:99, transition:'width 0.4s ease' }} />
      </div>
      <span style={{ fontSize:'0.72rem', fontWeight:700, color:bg, minWidth:32 }}>{pct}%</span>
    </div>
  );
}
