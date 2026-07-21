import React from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

export default function CollapsibleSection({
  id,
  title,
  expanded = true,
  onToggle,
  actions,
  children,
  className = '',
}) {
  const panelId = `dashboard-section-${id}`;

  return (
    <section className={`dashboard-section dashboard-section--collapsible${expanded ? ' dashboard-section--expanded' : ' dashboard-section--collapsed'} ${className}`.trim()}>
      <header className="dashboard-section__head">
        <button
          type="button"
          className="dashboard-section__toggle"
          aria-expanded={expanded}
          aria-controls={panelId}
          onClick={() => onToggle?.(id)}
        >
          {expanded ? <ChevronDown size={16} aria-hidden /> : <ChevronRight size={16} aria-hidden />}
          <h3 className="dashboard-section__title">{title}</h3>
        </button>
        {actions && <div className="dashboard-section__actions">{actions}</div>}
      </header>
      {expanded && (
        <div id={panelId} className="dashboard-section__body">
          {children}
        </div>
      )}
    </section>
  );
}
