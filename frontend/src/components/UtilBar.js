import React from 'react';

export default function UtilBar({ pct }) {
  const level = pct > 80 ? 'critical' : pct > 60 ? 'warning' : 'ok';

  return (
    <div className="util-bar">
      <div className="util-bar__track">
        <div
          className={`util-bar__fill util-bar__fill--${level}`}
          style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
        />
      </div>
      <span className={`util-bar__label util-bar__label--${level}`}>
        {pct}%
      </span>
    </div>
  );
}
