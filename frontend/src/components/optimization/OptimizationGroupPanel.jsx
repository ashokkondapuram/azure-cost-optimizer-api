import React, { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { formatCurrency } from '../../utils/format';

export default function OptimizationGroupPanel({
  groupKey,
  title,
  meta,
  count,
  savings = 0,
  savingsHint = '',
  currency = 'CAD',
  defaultOpen = true,
  open: controlledOpen,
  onOpenChange,
  scrollableBody = false,
  children,
}) {
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : internalOpen;

  const setOpen = (next) => {
    if (isControlled) onOpenChange?.(next);
    else setInternalOpen(next);
  };

  return (
    <section className={`opt-group-panel${open ? ' opt-group-panel--open' : ''}`}>
      <button
        type="button"
        className="opt-group-panel__header"
        onClick={() => setOpen(!open)}
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
            <span
              className="opt-group-panel__savings"
              title={savingsHint ? `${savingsHint} estimated savings for resources in this group` : undefined}
            >
              {formatCurrency(savings, { currency })}/mo
              {savingsHint && <span className="opt-group-panel__savings-hint">{savingsHint}</span>}
            </span>
          )}
        </div>
      </button>
      {open && (
        <div className={`opt-group-panel__body${scrollableBody ? ' opt-group-panel__body--scrollable' : ''}`}>
          {children}
        </div>
      )}
    </section>
  );
}
