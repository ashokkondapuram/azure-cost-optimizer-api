import React, { useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronUp, Columns, RotateCcw } from 'lucide-react';

export default function ColumnPicker({
  columns,
  visibleKeys,
  onToggle,
  onMove,
  onRestore,
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDoc = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  return (
    <div className="column-picker" ref={ref}>
      <button
        type="button"
        className="btn btn-ghost btn-sm"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="true"
      >
        <Columns size={14} aria-hidden />
        Columns
      </button>
      {open && (
        <div className="column-picker__menu card" role="menu">
          <p className="column-picker__title">Visible columns</p>
          {columns.map((col, idx) => {
            const checked = visibleKeys.includes(col.key);
            return (
              <div key={col.key} className="column-picker__row">
                <label className="column-picker__label">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => onToggle(col.key)}
                  />
                  <span>{col.label}</span>
                </label>
                <span className="column-picker__order">
                  <button
                    type="button"
                    className="btn btn-ghost btn-icon-only"
                    aria-label={`Move ${col.label} up`}
                    disabled={idx === 0}
                    onClick={() => onMove(col.key, 'up')}
                  >
                    <ChevronUp size={12} />
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-icon-only"
                    aria-label={`Move ${col.label} down`}
                    disabled={idx === columns.length - 1}
                    onClick={() => onMove(col.key, 'down')}
                  >
                    <ChevronDown size={12} />
                  </button>
                </span>
              </div>
            );
          })}
          <button type="button" className="btn btn-ghost btn-sm column-picker__restore" onClick={onRestore}>
            <RotateCcw size={12} aria-hidden />
            Restore defaults
          </button>
        </div>
      )}
    </div>
  );
}
