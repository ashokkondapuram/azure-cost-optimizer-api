import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { formatCurrency } from '../../utils/format';

export default function OptimizationGroupPanel({
  groupKey,
  title,
  meta,
  count,
  savings = 0,
  currency = 'CAD',
  defaultOpen = true,
  children,
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className={`opt-group-panel${open ? ' opt-group-panel--open' : ''}`}>
      <button
        type="button"
        className="opt-group-panel__header"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <ChevronDown size={16} className="opt-group-panel__chevron" aria-hidden />
        <div className="opt-group-panel__title-wrap">
          <h3 className="opt-group-panel__title">{title}</h3>
          {meta && <p className="opt-group-panel__meta">{meta}</p>}
        </div>
        <div className="opt-group-panel__stats">
          <span className="opt-group-panel__count">{count}</span>
          {savings > 0 && (
            <span className="opt-group-panel__savings">
              {formatCurrency(savings, { currency })}/mo
            </span>
          )}
        </div>
      </button>
      {open && (
        <div className="opt-group-panel__body">
          {children}
        </div>
      )}
    </section>
  );
}
