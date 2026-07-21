import React from 'react';
import { NavLink } from 'react-router-dom';
import { EXPLORER_TABS } from '../../context/CloudExplorerContext';
import { explorerPath } from '../../utils/nestedRoutes';

export default function WizExplorerTabs({ tab, counts = {} }) {
  return (
    <nav className="wiz-tabs" role="tablist" aria-label="Cloud explorer">
      {EXPLORER_TABS.map((item) => {
        const count = counts[item.id];
        const to = explorerPath(item.id);
        return (
          <NavLink
            key={item.id}
            to={to}
            end={item.id === 'overview'}
            role="tab"
            id={`wiz-tab-${item.id}`}
            aria-controls={`wiz-panel-${item.id}`}
            className={({ isActive }) => `wiz-tab${isActive ? ' wiz-tab--active' : ''}`}
          >
            {item.label}
            {typeof count === 'number' && count > 0 && (
              <span className="wiz-tab__count">{count > 999 ? '999+' : count}</span>
            )}
          </NavLink>
        );
      })}
    </nav>
  );
}
