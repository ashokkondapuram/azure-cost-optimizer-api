import React, { useState } from 'react';
import { ChevronDown, Info } from 'lucide-react';
import usePersistedState from '../hooks/usePersistedState';

export default function DrawerCollapsibleSection({
  title,
  icon = null,
  badge = null,
  hint = null,
  headerAction = null,
  defaultOpen = true,
  storageKey = null,
  variant = 'default',
  compact = false,
  onOpenChange = null,
  children,
}) {
  const [ephemeralOpen, setEphemeralOpen] = useState(defaultOpen);
  const persistKey = storageKey ? `drawer-section:${storageKey}` : null;
  const [persistedOpen, setPersistedOpen] = usePersistedState(
    persistKey || 'drawer-section:__unused',
    defaultOpen,
  );
  const open = persistKey ? persistedOpen : ephemeralOpen;
  const setOpen = persistKey ? setPersistedOpen : setEphemeralOpen;

  const toggleOpen = () => {
    setOpen((value) => {
      const next = !value;
      onOpenChange?.(next);
      return next;
    });
  };

  return (
    <section
      className={`insight-drawer__section insight-collapsible insight-collapsible--${variant}${open ? ' insight-collapsible--open' : ''}${compact ? ' insight-collapsible--compact' : ''}`}
    >
      <button
        type="button"
        className="insight-collapsible__header"
        onClick={toggleOpen}
        aria-expanded={open}
      >
        {icon && <span className="insight-collapsible__icon" aria-hidden>{icon}</span>}
        <span className="insight-collapsible__title">{title}</span>
        {badge != null && badge !== '' && (
          <span className="insight-collapsible__badge">{badge}</span>
        )}
        {headerAction && (
          <span className="insight-collapsible__header-action">{headerAction}</span>
        )}
        {variant === 'info' && !open && (
          <Info size={14} className="insight-collapsible__info-icon" aria-hidden />
        )}
        <ChevronDown size={16} className="insight-collapsible__chevron" aria-hidden />
      </button>
      {hint && !open && (
        <p className="insight-collapsible__hint text-muted">{hint}</p>
      )}
      {open && (
        <div className="insight-collapsible__body">
          {children}
        </div>
      )}
    </section>
  );
}
