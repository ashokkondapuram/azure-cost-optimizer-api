import React from 'react';

export default function Toggle({ checked, onChange, label, disabled }) {
  return (
    <label className={`toggle${disabled ? ' toggle--disabled' : ''}`}>
      <input
        type="checkbox"
        className="toggle-input"
        checked={checked}
        disabled={disabled}
        onChange={e => onChange(e.target.checked)}
      />
      <span className="toggle-track" aria-hidden="true">
        <span className="toggle-thumb" />
      </span>
      {label && <span className="toggle-label">{label}</span>}
    </label>
  );
}
