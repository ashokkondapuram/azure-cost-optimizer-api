import React from 'react';

/**
 * Shared shell for resource inventory pages — hero, sticky toolbar, scroll body, load-more footer.
 */
export default function ResourceInventoryPageShell({
  hero = null,
  toolbar = null,
  footer = null,
  children,
  className = '',
}) {
  return (
    <div className={`resource-inventory-shell${className ? ` ${className}` : ''}`}>
      {hero ? <div className="resource-inventory-shell__hero">{hero}</div> : null}
      {toolbar ? <div className="resource-inventory-shell__toolbar">{toolbar}</div> : null}
      <div className="resource-inventory-shell__body">
        {children}
      </div>
      {footer ? <div className="resource-inventory-shell__footer">{footer}</div> : null}
    </div>
  );
}
