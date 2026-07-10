import React from 'react';

/**
 * Shared shell for Optimization Hub tabs — consistent hero, sticky toolbar, scroll body, footer.
 */
export default function OptimizationHubTabShell({
  hero = null,
  toolbar = null,
  footer = null,
  children,
  className = '',
}) {
  return (
    <div className={`optimization-hub-tab-shell optimization-hub-panel__content${className ? ` ${className}` : ''}`}>
      {hero ? <div className="optimization-hub-tab-shell__hero">{hero}</div> : null}
      {toolbar ? <div className="optimization-hub-tab-shell__toolbar">{toolbar}</div> : null}
      <div className="optimization-hub-tab-shell__body">
        {children}
      </div>
      {footer ? <div className="optimization-hub-tab-shell__footer">{footer}</div> : null}
    </div>
  );
}
